# LiDAR & 360 Video Synchronization

Pipeline to synchronize georeferenced LiDAR alerts with non-georeferenced 360° timelapse videos using vehicle trajectory matching and temporal alignment.

## Prerequisites

**System:**
Requires `exiftool` to read binary video headers.

~~~bash
sudo apt-get install libimage-exiftool-perl
~~~

**Python:**

~~~bash
pip install pandas numpy scipy pyproj
~~~

## Project Structure

- `file_man.py`: Indexes files and extracts precise metadata (Start Time/Duration) using ExifTool.
- `sync.py`: Handles spatial KDTree search (trajectory matching) and temporal conversion.
- `main.py`: Entry point for configuration and pipeline execution.
- `data/`: Input directory containing `las` (alerts source), `csv` (trajectories), and `video` folders.

## Configuration

Adjust the following constants in `main.py` before running:

- `FPS`: Frame rate of the video files (e.g., 29.97).
- `TIMELAPSE_RATIO`: Expansion factor for timelapse videos (Formula: FPS * Capture_Interval).
- `GPS_TO_VIDEO_OFFSET`: Timezone difference between LiDAR GPS data and Camera clock (e.g., -3).

## Usage

1. Organize input files into `./data/csv` and `./data/video`.
2. Run the script:

~~~bash
python main.py
~~~

The output will be a JSON array containing the matched video filename, precise timestamp, and frame number for each alert.

## Troubleshooting

- **`[Errno 2] No such file or directory: 'exiftool'`**: Install system dependency.
- **`status: NO_VIDEO_COVERAGE`**: Check `GPS_TO_VIDEO_OFFSET` in `main.py`.
- **`status: ERROR_NO_TRAJ_FILE`**: No trajectory CSV found for the LAS date.