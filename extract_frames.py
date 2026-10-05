import cv2
import os
import argparse
import numpy as np
from tqdm import tqdm

def extract_frames(video_path, output_dir, mode="all", step=1, fps_target=None, motion_thresh=1.5, image_format="jpg", prefix="frame"):
    if not os.path.exists(video_path):
        print(f"Error: Video file '{video_path}' not found.")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file '{video_path}'.")
        return

    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration_sec = total_video_frames / fps if fps > 0 else 0

    # Calculate step if target FPS is specified
    if fps_target is not None and fps_target > 0:
        step = max(1, int(round(fps / fps_target)))

    print("=" * 60)
    print("Video Information:")
    print(f"  File: {video_path}")
    print(f"  Total Video Frames: {total_video_frames:,}")
    print(f"  Original FPS: {fps:.2f}")
    print(f"  Duration: {duration_sec:.2f}s ({duration_sec / 60:.2f} minutes)")
    print(f"  Extraction Mode: {mode.upper()}")
    
    if mode == "step":
        estimated_frames = (total_video_frames + step - 1) // step
        effective_fps = fps / step
        print(f"  Step Setting: Every {step} frame(s) (~{effective_fps:.1f} FPS)")
        print(f"  Estimated Frames to Save: ~{estimated_frames:,}")
    elif mode == "motion":
        print(f"  Motion Threshold: {motion_thresh}% pixel change")
        print(f"  Sample Check Interval: Every {step} frame(s)")
        print(f"  Estimated Frames to Save: Dynamic (only when movement occurs)")

    print(f"  Output Directory: {os.path.abspath(output_dir)}")
    print(f"  Filename Prefix: {prefix}")
    print("=" * 60)

    os.makedirs(output_dir, exist_ok=True)
    digits = len(str(total_video_frames))

    frame_idx = 0
    saved_count = 0

    prev_gray = None

    with tqdm(total=total_video_frames, desc="Processing Video", unit="frame") as pbar:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            should_save = False

            if mode == "step" or mode == "all":
                if frame_idx % step == 0:
                    should_save = True

            elif mode == "motion":
                # Convert to gray and blur to diminish noise
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if prev_gray is None:
                    should_save = True
                    prev_gray = gray
                else:
                    if frame_idx % step == 0:
                        diff = cv2.absdiff(prev_gray, gray)
                        thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                        motion_percent = (np.count_nonzero(thresh) / thresh.size) * 100.0

                        if motion_percent >= motion_thresh:
                            should_save = True
                            prev_gray = gray

            if should_save:
                saved_count += 1
                filename = f"{prefix}_{saved_count:0{digits}d}.{image_format}"
                out_path = os.path.join(output_dir, filename)
                cv2.imwrite(out_path, frame)

            frame_idx += 1
            pbar.update(1)

    cap.release()
    print("\nExtraction Complete!")
    print(f"Successfully saved {saved_count:,} frames to '{output_dir}'.")
    reduction = ((total_video_frames - saved_count) / total_video_frames) * 100 if total_video_frames > 0 else 0
    print(f"Frame Count Reduction: {reduction:.1f}% fewer frames saved!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and reduce video frames while preserving all movements.")
    parser.add_argument("--video", type=str, default=r"C:\Users\RohithSuryaCKM\Videos\Screen Recordings\Screen Recording 2026-09-29 110701.mp4", help="Path to input video file")
    parser.add_argument("--output", type=str, default="frames", help="Output directory for saved frames")
    parser.add_argument("--prefix", type=str, default="frame", help="Prefix for saved frame image filenames")
    parser.add_argument("--mode", type=str, choices=["all", "step", "motion"], default="motion", 
                        help="Extraction mode: 'motion' (smart motion detection), 'step' (interval sampling), or 'all'")
    parser.add_argument("--fps", type=float, default=None, help="Target FPS to extract (e.g. --fps 2 for 2 frames/sec)")
    parser.add_argument("--step", type=int, default=5, help="Check frame interval / step (default: 5)")
    parser.add_argument("--thresh", type=float, default=1.5, help="Motion detection sensitivity threshold in %% (default: 1.5)")
    parser.add_argument("--format", type=str, default="jpg", choices=["jpg", "png"], help="Output image format")

    args = parser.parse_args()

    # If --fps or --step is passed explicitly while mode is default, adjust mode if appropriate
    mode = args.mode
    if args.fps is not None and args.mode == "motion":
        mode = "step"

    extract_frames(
        video_path=args.video,
        output_dir=args.output,
        mode=mode,
        step=args.step,
        fps_target=args.fps,
        motion_thresh=args.thresh,
        image_format=args.format,
        prefix=args.prefix
    )
