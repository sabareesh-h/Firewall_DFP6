import cv2
import os
import argparse

def extract_frames(video_path, output_dir, target_fps=2):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return
        
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Original video FPS: {original_fps}")
    
    # Fallback if FPS cannot be read properly
    if original_fps == 0 or original_fps != original_fps:
        original_fps = 30
        
    frame_interval = max(1, round(original_fps / target_fps))
    print(f"Extracting 1 frame every {frame_interval} frames to achieve ~{target_fps} FPS")
    
    frame_count = 0
    saved_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_count % frame_interval == 0:
            output_path = os.path.join(output_dir, f"frame_{saved_count:05d}.jpg")
            cv2.imwrite(output_path, frame)
            saved_count += 1
            
        frame_count += 1
        
    cap.release()
    print(f"Extraction complete! Saved {saved_count} frames to '{output_dir}'")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Extract frames from a video at a specific FPS")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output", "-o", default="extracted_frames", help="Output directory for frames")
    parser.add_argument("--fps", type=float, default=2, help="Target FPS to extract")
    args = parser.parse_args()
    
    extract_frames(args.video_path, args.output, args.fps)
