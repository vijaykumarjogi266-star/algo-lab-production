import yt_dlp
import pandas as pd
import json
from datetime import datetime

# The Target Channels
CHANNELS = [
    {"name": "QuantInsti", "url": "https://www.youtube.com/@QuantInsti/videos"},
    {"name": "DhanHQ", "url": "https://www.youtube.com/@DhanHQ/videos"},
    {"name": "ProTradingArt", "url": "https://www.youtube.com/@ProTradingArt/videos"}
]

def harvest_youtube_data():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📡 Starting YouTube Strategy Harvester...")
    
    ydl_opts = {
        'extract_flat': True,       # Don't download the video, just get metadata
        'playlist_items': '1-5',    # Only get the 5 most recent videos per channel
        'quiet': True,
        'no_warnings': True
    }

    all_videos = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for channel in CHANNELS:
            print(f"  -> Scraping latest videos from {channel['name']}...")
            try:
                result = ydl.extract_info(channel['url'], download=False)
                if 'entries' in result:
                    for video in result['entries']:
                        all_videos.append({
                            "Channel": channel['name'],
                            "Title": video.get('title'),
                            "URL": video.get('url'),
                            "Duration (sec)": video.get('duration'),
                            "Views": video.get('view_count')
                        })
            except Exception as e:
                print(f"  [WARN] Failed to scrape {channel['name']}: {e}")

    # Save to a report
    if all_videos:
        df = pd.DataFrame(all_videos)
        csv_path = "/home/ubuntu/algolab/data/youtube_algo_strategies.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n✅ Successfully harvested {len(all_videos)} recent videos. Saved to {csv_path}")
        print("\n--- LATEST ALGO TRADING VIDEOS ---")
        print(df[['Channel', 'Title']].head(15).to_string(index=False))
    else:
        print("❌ No videos found.")

if __name__ == "__main__":
    harvest_youtube_data()
