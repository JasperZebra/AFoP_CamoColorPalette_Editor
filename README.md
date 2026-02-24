

# AFoP_CamoColorPalette_Editor
A lightweight modding tool for Avatar: Frontiers of Pandora that lets you edit gear and weapon camo color palettes directly inside .rejuice files — no hex editor required.

<img width="957" height="731" alt="image" src="https://github.com/user-attachments/assets/1caf3b1b-70da-48a6-8821-45dc177da177" />

## How to Use

1. **Open your file** — click **📂 Open** and browse to your `gearcamo_colorpalettes.rejuice`, or place it in the same folder as the tool and it will load automatically on launch.

2. **Find the entry you want to edit** *(optional)* — use the 🔍 search bar to filter by name **(e.g. type `res` or `vlt` to narrow down the list)**

3. **Double-click a color cell** — click any cell in the **myPrimaryColor**, **mySecondaryColor**, or **myTertiaryColor** column to open the color picker.
   - Drag the **gradient square** to set saturation and brightness.
   - Drag the **rainbow bar** to shift the hue.
   - Type a **hex code** directly, or adjust the **R G B sliders**.
   - The **Before / After** strip shows your change live.
   - Entries showing **—** have no color defined for that slot and cannot be edited.

4. **Click ✓ Apply** to confirm the new color, or **✗ Cancel** to discard it.

5. **Click 💾 Save** when you're done — the tool writes your changes back into the `.rejuice` file and automatically creates a `.bak` backup of the original.
