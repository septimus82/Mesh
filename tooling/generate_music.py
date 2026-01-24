import math
import os
import struct
import sys
import wave


def generate_music_loop(filename, duration=5.0, bpm=120, style="dungeon"):
    sample_rate = 44100
    n_frames = int(sample_rate * duration)
    beat_duration = 60 / bpm

    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        if style == "dungeon":
            notes = [220, 261.63, 329.63, 392.00] # A minor
        elif style == "forest":
            notes = [261.63, 329.63, 392.00, 523.25] # C major
        else:
            notes = [440, 440, 440, 440]

        for i in range(n_frames):
            t = i / sample_rate

            # Determine current beat and note
            beat_index = int(t / beat_duration)
            note_freq = notes[beat_index % len(notes)]

            # Basic sine wave
            value = math.sin(2 * math.pi * note_freq * t)

            # Add a lower bass note every 4 beats
            if (beat_index // 4) % 2 == 0:
                value += 0.5 * math.sin(2 * math.pi * (notes[0]/2) * t)

            # Normalize roughly
            value = value * 0.3

            data = int(value * 32767.0)
            # Clip
            data = max(-32767, min(32767, data))

            wav_file.writeframes(struct.pack('<h', data))

    print(f"Generated {filename}")

if __name__ == "__main__":
    os.makedirs("assets/music", exist_ok=True)

    if len(sys.argv) > 1:
        style = sys.argv[1]
        filename = f"assets/music/{style}_theme.wav"
        generate_music_loop(filename, duration=4.0, bpm=100, style=style)
    else:
        generate_music_loop("assets/music/dungeon_theme.wav", duration=4.0, bpm=120, style="dungeon")
