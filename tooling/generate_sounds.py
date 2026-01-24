import math
import os
import random
import struct
import wave


def generate_tone(filename, frequency=440, duration=0.1, volume=0.5, wave_type='sine'):
    sample_rate = 44100
    n_frames = int(sample_rate * duration)

    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        for i in range(n_frames):
            t = i / sample_rate
            if wave_type == 'sine':
                value = math.sin(2 * math.pi * frequency * t)
            elif wave_type == 'square':
                value = 1.0 if math.sin(2 * math.pi * frequency * t) > 0 else -1.0
            elif wave_type == 'sawtooth':
                value = 2.0 * (t * frequency - math.floor(0.5 + t * frequency))
            elif wave_type == 'noise':
                value = random.uniform(-1, 1)
            else:
                value = 0.0

            # Apply envelope (fade out)
            envelope = 1.0 - (i / n_frames)

            data = int(value * volume * envelope * 32767.0)
            wav_file.writeframes(struct.pack('<h', data))

    print(f"Generated {filename}")

def generate_slide(filename, start_freq=440, end_freq=880, duration=0.2, volume=0.5):
    sample_rate = 44100
    n_frames = int(sample_rate * duration)

    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        for i in range(n_frames):
            t = i / sample_rate
            progress = i / n_frames
            freq = start_freq + (end_freq - start_freq) * progress

            value = math.sin(2 * math.pi * freq * t)
            data = int(value * volume * 32767.0)
            wav_file.writeframes(struct.pack('<h', data))

    print(f"Generated {filename}")

def main():
    os.makedirs("assets/sounds", exist_ok=True)

    # UI Sounds
    generate_tone("assets/sounds/ui_hover.wav", frequency=800, duration=0.05, volume=0.2, wave_type='sine')
    generate_tone("assets/sounds/ui_click.wav", frequency=1200, duration=0.1, volume=0.3, wave_type='sine')
    generate_slide("assets/sounds/ui_open.wav", start_freq=400, end_freq=800, duration=0.2, volume=0.3)
    generate_slide("assets/sounds/ui_close.wav", start_freq=800, end_freq=400, duration=0.2, volume=0.3)

    # Combat Sounds
    generate_tone("assets/sounds/attack.wav", frequency=0, duration=0.15, volume=0.4, wave_type='noise') # Whoosh
    generate_tone("assets/sounds/shoot.wav", frequency=600, duration=0.1, volume=0.4, wave_type='sawtooth') # Pew
    generate_tone("assets/sounds/hit.wav", frequency=150, duration=0.1, volume=0.5, wave_type='square') # Crunch
    generate_slide("assets/sounds/die.wav", start_freq=300, end_freq=50, duration=0.5, volume=0.5) # Falling

    # Misc
    generate_tone("assets/sounds/footstep.wav", frequency=0, duration=0.05, volume=0.1, wave_type='noise')

if __name__ == "__main__":
    main()
