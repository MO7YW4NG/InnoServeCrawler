"""
InnoServeCrawler Main Module

This module scrapes competition data from the InnoServe website,
downloads audio from YouTube links, transcribes the audio,
labels the transcriptions using Google Gemini, and saves the
results into a CSV file.

Modules Used:
- aiohttp for asynchronous HTTP requests.
- BeautifulSoup for HTML parsing.
- yt_dlp for downloading YouTube videos as audio.
- dotenv for loading environment variables.
- groq and google.genai for API calls.
"""

import asyncio
import csv
import json
import os
import re

import aiohttp
import dotenv
import yt_dlp
from bs4 import BeautifulSoup

from groq import Groq
from google import genai
from google.genai import types

# Load environment variables from .env file
dotenv.load_dotenv(override=True)

# Initialize API clients with keys from environment variables
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def scrape_competition_data(html_content, year):
    """
    Scrape competition data from HTML content for a given year.

    Parameters:
        html_content (str): HTML content to parse.
        year (int): The competition year (e.g., 25, 26, ...)

    Returns:
        list of dict: A list containing competition results with keys:
            "屆數", "組別", "名次", "學校", "標題", "YOUTUBE連結".
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'id': 'ctl00_ContentPlaceHolder1_gv_award'})
    
    if not table:
        print("Table not found in HTML content")
        return []
    
    results = []
    rows = table.find_all('tr')[1:]  # Skip header row

    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 7:
            group = cells[0].text.strip()
            rank = cells[1].text.strip()
            school = cells[3].text.strip()
            title_cell = cells[4]
            title_text = title_cell.get_text(strip=True)
            # Remove characters that are not allowed in filenames
            title_text = re.sub(r'[\\/*?:"<>|]', "", title_text)
            youtube_link = ""
            link_tag = title_cell.find('a')
            if link_tag and link_tag.has_attr('href'):
                youtube_link = link_tag['href']
            
            results.append({
                "屆數": year,
                "組別": group,
                "名次": rank,
                "學校": school,
                "標題": title_text,
                "YOUTUBE連結": youtube_link,
            })
    
    return results


def save_to_csv(data, filename="competition_results.csv"):
    """
    Save the competition results data to a CSV file.

    Parameters:
        data (list of dict): The competition results.
        filename (str): The name of the CSV file to write.
    """
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["屆數", "組別", "名次", "學校", "標題", "YOUTUBE連結", "摘要", "關鍵技術"])
        for item in data:
            writer.writerow([
                item["屆數"],
                item["組別"],
                item["名次"],
                item["學校"],
                item["標題"],
                item["YOUTUBE連結"],
                item.get("摘要", "無資訊"),
                item.get("關鍵技術", "[]")
            ])
    
    print(f"Data saved to {filename}")


async def label_data(results, output_dir="downloads"):
    """
    Use Google Gemini to label each result by generating a summary and key technologies.
    If the transcript file (TXT) for a result does not exist or contains specific strings,
    defaults are added.

    Parameters:
        results (list of dict): The competition data.
        output_dir (str): The directory where transcript files are stored.

    Returns:
        list of dict: The updated results with "摘要" and "關鍵技術".
    """
    generate_content_config = types.GenerateContentConfig(
        temperature=0.5,
        response_mime_type="application/json",
        response_schema=types.Schema(
            type=types.Type.OBJECT,
            required=["關鍵技術", "摘要"],
            properties={
                "關鍵技術": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                ),
                "摘要": types.Schema(type=types.Type.STRING),
            },
        ),
        system_instruction=[
            types.Part.from_text(text=(
                "替專案內容進行分析，逐字稿可能會有錯字，請用你的知識修正補齊，"
                "最終回傳關鍵技術和摘要，以精確的文字回覆，以繁體中文為主。"
                "若分析不出專案內容（如逐字稿內容為字幕、志願者等無效資訊），回傳```無資訊```；"
                "關鍵技術越仔細越好（如OCR、RAG、LLM模型名稱、YOLO等），但不要超過6個技術。"
            )),
        ],
    )

    for result in results:
        transcript_path = os.path.join(output_dir, f"{result['標題']}.txt")
        if not os.path.exists(transcript_path):
            result["關鍵技術"] = "[]"
            result["摘要"] = "無資訊"
            continue

        with open(transcript_path, mode='r', encoding='utf-8') as f:
            transcript_text = f.read()
        
        if '字幕提供' in transcript_text or '志願者' in transcript_text:
            result["關鍵技術"] = "[]"
            result["摘要"] = "無資訊"
            continue

        # Attempt to generate labels using Google Gemini
        while True:
            try:
                response = await gemini_client.aio.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=['#標題', result['標題'], '#影片逐字稿內容', transcript_text],
                    config=generate_content_config
                )
                label_response = json.loads(response.text)
                result["關鍵技術"] = str(label_response["關鍵技術"])
                result["摘要"] = label_response["摘要"]
                print(f"{result['標題']}: {result['摘要']}")
                print("關鍵技術:" + str(result["關鍵技術"]))
                break
            except Exception as e:
                print(f"Failed to label text for {result['標題']}: {e}")
                continue

    return results


async def download_audio_from_youtube(result, output_dir="downloads"):
    """
    Download audio from a YouTube URL and convert it to MP3 using yt-dlp and ffmpeg.
    
    Parameters:
        result (dict): A competition result containing a YouTube link.
        output_dir (str): The directory to save the downloaded audio.
    """
    if "YOUTUBE連結" not in result or not result["YOUTUBE連結"]:
        print("No YouTube link provided for:", result.get("標題"))
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, f"{result['標題']}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([result["YOUTUBE連結"]])
    except Exception as e:
        print(f"Failed to download audio from {result['YOUTUBE連結']}: {e}")


def transcribe_audio(filename, output_dir="downloads"):
    """
    Transcribe the audio file for a given title using the Groq client.

    Parameters:
        filename (str): The title corresponding to the audio file.
        output_dir (str): The directory where the audio and transcript are stored.
    """
    audio_path = os.path.join(output_dir, f"{filename}.mp3")
    transcript_path = os.path.join(output_dir, f"{filename}.txt")
    try:
        with open(audio_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                file=(audio_path, audio_file.read()),
                model="whisper-large-v3",
                prompt="Specify context or spelling, respond in Traditional Chinese (zh-TW)",
                response_format="text",
                language="zh",
                temperature=0.01
            )
        with open(transcript_path, "w", encoding='utf-8') as transcript_file:
            transcript_file.write(transcription)
    except Exception as e:
        print(f"Transcription failed for {filename}: {e}")


async def main():
    """
    Main function orchestrating the data scraping, audio processing,
    transcription, and labeling workflow.
    """
    results = []
    # Create an asynchronous HTTP session with custom headers.
    async with aiohttp.ClientSession(headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0')
    }) as session:
        # Loop through competition years (e.g., 25 to 29).
        for year in range(25, 30):
            data = {
                '__VIEWSTATEGENERATOR': '362C9F34',
                '__VIEWSTATE': 'CgP1/QbQHzFEi8nWVFxVT2CUBa0MRZ3PmTG4B42k2ivK4DLj65h52P3Zju4DMitvdqczd8DIO0f1VdmzkkX417a9E+16KtCotlCWaf2WyPsJAMcKh8EXjsyV3pJqjluyHUboD7kv+XX2oQE9r9S6jeeOPhnZ9DUEZDfkjml27dbFKuTyrOAuvn3daV8F+yjugb8mjxmIq4JTVHqLBMheEc5zHFJSbsN608wC4MZGCH3RZ3NPeMnsJRZQHDmiw9FL2Uc+YVUfKE7Luf29JG+sYSbt0BZPbo+MEgC54dDs/E6cwSqaDJVT12wVLpT+6wSWQBEOITcsVYlhaRF/FATitAZmTBry5HvosMaeiOXDlIiz42CfazgnD83+jqT9sIXDonV5scxgmvQ0YTvwz4rbXCEYVE2lsBycH/3FjXxBwyU9x0L/+OUh/3iaBu4rlXvTC/LH92KPRWp/YGXwWK4NsUqzrQ+VKaCwVIjvcIBsQnb2tr2RVRFCrC4NHJx/s8K7WBr86Zy7aHlp+0eqFCE54cjJgKvaWUMGvbUJ1Y9JTm7/ZPQJs0A//d6j4gIKpTokdTtf5TXhRwUNnWO6LqWwDB5TYbiP5f5kouDtfcV2mEQQYWx5oBsLDxGRYSdA18iPbp4Fd5hip1s2IFiNu7WafSidEjs7J3gAeVM2j6PmJH9oyjKt13hpgMN1HA3PCaw0U2B2mYQY1B4jj/KdpUpFaNVBey9YN9IjEc5yMkiBvNDYM9DVU/OuIELQ9wkjbEfL5HomCzna7q4aSIjg5yf1+a8g24lqci+t4rKfdjGTIAuEYvHsG0JB059IWsqcNVngUU0MwJ1dnA953MafTTdW68mZrNnw+x2D7lBDRojhxbUaE3HqJSKti5BC8bvX3VCuS3DN65ebNL7sp3jU6mXS5idTwIwBt+X32SvQw1wY+COEmXUt5BbwNasvSwUvTFmt7gJJ4cdqG4nimnnmmfETgrlONVgAmQAU10++OGTaCAzRsIzFzAphspTz1bsBkcwzuRkMRyifwp/OZSQc9ensNks/CiouoRLQ09nGt+3TyQT9OIvEcV0Dndzg3AnltihEbTSESY/wOQNaLCF2CfuqcyPEZV8DZX1Snte1M93lJeOhM6z8O7VUTD0VySE5hpljJsY4IuRSzAAKXGDTnPF5P3OBENECs4iWbgPlWLtF4mBwmJcEx1E58v91JvWEOnPrlefixtxKjltu87V9pTZchAwZgPAc3T87N1O8XNo7f8EXQo6NkgtULOAm1laebIXlyBP3Ya5RmC8eToqAWz66bH4wvFphmrdfz9V1CP7KPHCJJ8pFqIw0H8c9T9dBqV8QEfNL7Zphr/uahAEUO/g3uA79nXRtv4Sdq5PeVkHS4f/h/cHmpXlzIe3VNK6LyTmxwFaElIUsHsHwGVTg3259lUuYumswXVAhPdijr3+UuIRjCH0vAZT845f4OKKWtir+ttMJlnkAFLUBhEHso9niHyuRyAlzdAuiusTwICUz1BA6nrOgaLRBJ0lODcmYmEMrdmF6uk7SeKbQnma3DVz/nqFUx0tiLj6S7OKsW3O3fnEJDU1O+vZ6EDqB5kIVJEIj5xJXbi8ID9DDp5wXcDOfOvB4CXMXuBvNwBST2lfLVNgJSBRVdIcD0CDUG+4o2SVCiqGWX6B4XLoCg0eLyI3j5Z5klITJZQl/xqo8m8RV9mLK6AQ8Mfn0VLMFRB7E4zrfhrNWhvdUWzN7jt2YIZkXsce+vW7YAT2qtCGmz8T83RywrGELMbYDBbLkI7rkRmvq1Ag8S/DTA07T8G12aFKUcA6rqJXAtjR1or4UVLSE/KBQoHCx3/uHIzPpV/9VEOdPXU15flQNkwW39by98tZIn9jMtOE'
            }
            # End of POST data for scraping.
            response_text = await session.post(
                'https://innoserve.tca.org.tw/award.aspx', data=data
            )
            # Scrape and extend results with data for the current year.
            results.extend(scrape_competition_data(await response_text.text(), year))
    
    # Download audio for each result if the MP3 doesn't exist.
    for result in results:
        audio_file = os.path.join("downloads", f"{result['標題']}.mp3")
        if os.path.exists(audio_file):
            continue
        if "YOUTUBE連結" not in result or not result["YOUTUBE連結"]:
            continue
        await download_audio_from_youtube(result)
    
    # Transcribe audio files that have been downloaded but not yet transcribed.
    for result in results:
        audio_file = os.path.join("downloads", f"{result['標題']}.mp3")
        transcript_file = os.path.join("downloads", f"{result['標題']}.txt")
        if not os.path.exists(audio_file):
            continue
        if os.path.exists(transcript_file):
            continue
        print(f"Transcribing {result['標題']}...")
        transcribe_audio(result['標題'])
        await asyncio.sleep(10)
    
    # Label the results using Google Gemini.
    results = await label_data(results)
    
    # Save the final results to a CSV file.
    save_to_csv(results)


if __name__ == "__main__":
    asyncio.run(main())
