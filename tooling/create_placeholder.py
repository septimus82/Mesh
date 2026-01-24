"""Generate a simple placeholder sprite for the Mesh engine."""

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    target = Path("assets/placeholder.png")
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 64
    img = Image.new("RGBA", (size, size), (90, 160, 90, 255))
    draw = ImageDraw.Draw(img)

    inset = 6
    draw.rectangle(
        [inset, inset, size - inset - 1, size - inset - 1],
        outline=(255, 255, 255, 255),
        width=4,
    )
    center = size // 2
    draw.line([inset * 1.5, center, size - inset * 1.5, center], fill=(255, 255, 255, 255), width=4)
    draw.line([center, inset * 1.5, center, size - inset * 1.5], fill=(255, 255, 255, 255), width=4)

    img.save(target)
    print(f"Placeholder sprite written to {target.resolve()}")


if __name__ == "__main__":
    main()
