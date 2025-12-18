# from youtube_transcript_api import YouTubeTranscriptApi

# ytt_api = YouTubeTranscriptApi()

# transcript = ytt_api.fetch("WzvMdAEzAAk")

# text_list = [snippet.text for snippet in transcript.snippets]

# full_text = " ".join(text_list)

# print(full_text)

# import jwt
from Repository.Youtube import Youtube
from utils.helpers import format_date
yt = Youtube()

videos = yt.get_recent_videos("UCbEd9lNwkBGLFGz8ZxsZdVA")
# i = 0
for v in videos:
    # if i == 1:
    #     break
    meta = yt.get_title_description(v["videoId"])
    title , description = meta["title"] , meta["description"] 
    transcript = yt.get_transcript(v["videoId"])
    
    jobs_data = yt.extract_jobs_with_gemini(title,description,transcript)
    
    for company in jobs_data["openings"]:
        print("=" * 25)
        print(f"Company : {company["company"]}")
        print(f"Role : {company["role"]}")
        print(f"Employment Type : {company["employmentType"]}")
        print(f"Required Skills : {company["requiredSkills"]}")
        print(f"Work Mode : {company["workMode"]}")
        print(f"Location : {company["location"]}")
        print(f"Apply Link : {company["applyLink"]}")
        
        # i+= 1
        
    
    
    
    
