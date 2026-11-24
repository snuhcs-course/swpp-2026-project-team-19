# Launcher icon variants

Alternative color variants of the BottleMap launcher icon. They are not part of any source set, so the build ignores them; the app uses the `original` variant in `src/main/res`.

Each variant has the same layout as the icon in `src/main`:

- `res/mipmap-anydpi/ic_launcher.xml`, `ic_launcher_round.xml`: adaptive icon (color background, bitmap foreground).
- `res/mipmap-*dpi/ic_launcher_foreground.webp`: the 512x512 artwork scaled into the 72dp visible area of a 108dp layer, lossless WebP.
- `res/values/ic_launcher_background.xml`: the artwork's edge color.
- `ic_launcher-playstore.png`: the 512x512 artwork for store listings.

To switch the app to a variant, copy its `res/` over `src/main/res/` and its `ic_launcher-playstore.png` over `src/main/ic_launcher-playstore.png`. The file names match, so the manifest needs no change.

| Variant | Background |
|---|---|
| amber | `#E1C395` |
| sepia | `#EADED2` |
| night | `#272318` |
