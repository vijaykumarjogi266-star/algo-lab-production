import yt_dlp
import pandas as pd
import json
import re
from datetime import datetime

CHANNELS = [
    {"name": "QuantInsti", "url": "https://www.youtube.com/@QuantInsti/videos"},
    {"name": "DhanHQ", "url": "https://www.youtube.com/@DhanHQ/videos"},
    {"name": "ProTradingArt", "url": "https://www.youtube.com/@ProTradingArt/videos"}
]

def harvest_deep_data():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📡 Deep Scanning ALL Videos for Strategy Code & Links...")
    
    # We remove 'playlist_items' to get ALL videos on the channel.
    # extract_flat=True ensures it only grabs metadata (super fast) instead of downloading video files.
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True
    }

    all_videos = []
    total_code_links_found = 0

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for channel in CHANNELS:
            print(f"  -> Scanning entire channel library: {channel['name']}...")
            try:
                result = ydl.extract_info(channel['url'], download=False)
                if 'entries' in result:
                    # Filter out None entries (failed extractions)
                    entries = [e for e in result['entries'] if e is not None]
                    print(f"     Found {len(entries)} videos.")
                    
                    for video in entries:
                        # Extract description to find GitHub or Strategy links
                        desc = video.get('description', '') or ''
                        
                        # Find all URLs in the description
                        urls = re.findall(r'(https?://[^\s]+)', desc)
                        
                        # Filter for high-value quant resources (GitHub, Colab, Google Drive, Sensibull)
                        strategy_links = [url for url in urls if 'github.com' in url or 'colab.research' in url or 'drive.google.com' in url or 'sensibull' in url or 'streak' in url]
                        
                        if strategy_links:
                            total_code_links_found += len(strategy_links)

                        all_videos.append({
                            "Channel": channel['name'],
                            "Title": video.get('title'),
                            "URL": video.get('url'),
                            "Views": video.get('view_count'),
                            "Duration (sec)": video.get('duration'),
                            "Extracted_Code_Links": " | ".join(strategy_links) if strategy_links else "None",
                            # We don't save the full description to CSV to keep it clean, just the extracted value
                        })
            except Exception as e:
                print(f"  [WARN] Failed to scrape {channel['name']}: {e}")

    if all_videos:
        df = pd.DataFrame(all_videos)
        csv_path = "/home/ubuntu/algolab/data/youtube_deep_strategy_database.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n✅ Deep Scan Complete!")
        print(f"✅ Total Videos Analyzed: {len(all_videos)}")
        print(f"✅ Total Strategy/Code Links Extracted: {total_code_links_found}")
        print(f"✅ Master Database saved to {csv_path}\n")
        
        # Display the ones that actually contain code links
        with_links = df[df['Extracted_Code_Links'] != "None"]
        if not with_links.empty:
            print("--- TOP VIDEOS WITH SOURCE CODE / STRATEGY LINKS ---")
            print(with_links[['Channel', 'Title']].head(10).to_string(index=False))

if __name__ == "__main__":
    harvest_deep_data()
