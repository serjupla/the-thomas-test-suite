# The Thomas — Logo & Brand Assets

This directory contains the vector brand assets for The Thomas Test
Suite. 

## Variants

| File | Description | Used in |
|---|---|---|
| `thomas-logo.svg` | Full logo (icon + wordmark), light variant — dark text/icon on a transparent background, intended for light backgrounds. | Main `README.md` (light theme), future self-contained HTML report template. |
| `thomas-logo-dark.svg` | Full logo (icon + wordmark), dark variant — light text/icon on a transparent background, intended for dark backgrounds. | Main `README.md` via `<picture>`, selected automatically when the viewer's OS/GitHub theme is dark. |
| `thomas-icon.svg` | Icon only, 1:1 aspect ratio. | Base artwork for the favicon and for `social-preview.png` (GitHub social preview image). |

`social-preview.png` (~1280×640) is a rendered composition derived from
`thomas-icon.svg`, configured as this repository's GitHub social preview
image (Settings → Social preview).

## Usage in README

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo/thomas-logo-dark.svg">
  <img src="assets/logo/thomas-logo.svg" alt="The Thomas logo" width="360">
</picture>
```

The `<img>` fallback (`thomas-logo.svg`) ensures the logo still renders
correctly for viewers/clients that don't support the `<picture>` element
or `prefers-color-scheme` media queries.

## Trademark policy

**"The Thomas" name and this logo are the project's brand**, protected
separately from the Apache 2.0 code license (see `LICENSE`, Section 6,
and `NOTICE`). Forks are free to reuse the source code under Apache 2.0
terms, but must not present themselves publicly as "The Thomas," and must
not reuse this name or these logo assets to do so. A fork is welcome to
adopt its own distinct name and visual identity.
