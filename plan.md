## SIDEBAR FIXES

- [x] All sidebar text colors must be changed to our white tone (#faf9f5). Currently the texts appear grey and only turn white on hover — make them permanently #faf9f5.
- [x] A vertical divider line is missing from the sidebar — add it.
- [x] The sidebar is currently set to close on every page change, refresh, or any other activity. Reverse this behavior: the default state should be OPEN. The user can manually close it and reopen it. It should no longer auto-close.
- [x] Hover background on non-active sidebar items is visible and matches active state color/opacity.

---

## DASHBOARD — UPLOAD AREA

- [x] In the upload area, there are two tabs: "Link" and "File". Currently, if the user is on the "Link" tab and drags a file onto the page, it does not get picked up. Fix this: even when the "Link" tab is active, if the user drags a file anywhere on the page, it should be accepted. When a file is being dragged over the page, show a "Drop your file here" label in the center. If the user drags out without dropping (drag leave), the box should return to its normal state.
- [x] In the "File" tab, there is a "Browse file" button. Keep it, but also make the entire drop zone area clickable — clicking anywhere on that zone should open the file picker, not just the "Browse file" button.

---

## DASHBOARD — "POWERED BY AI" SECTION

- [x] Remove the heading text "Unique features that set us apart" — this will cause the cards to shift slightly upward, which is the desired result.
- [x] The small icons inside the feature cards should be colorized with gradients (do not change the icon shapes, only add color):
  - Channel DNA icon → golden yellow gradient
  - Content Finder icon → blue gradient
  - Director icon → vibrant green gradient
  - The icons should be scaled up by ~25% within their background container but must NOT overflow outside the container. If 25% causes overflow, reduce accordingly.
- [x] Add a horizontal card slider / card carousel to this section. Cards that don't fit in the visible area should use a "Partial Visibility" design (the next card is partially visible at the edge to hint at scrolling).
  - Add 3 new cards to the existing 3: "Editor", "Analytics", and "Calendar". Editor and Analytics already exist as pages in the app — link them. Calendar does not exist yet — add the card with the same design but no link/action on click.
  - When the slider is at the leftmost position, the left arrow should disappear. When at the rightmost position, the right arrow should disappear.
  - Arrow buttons should only be visible when the user hovers over the cards section. When not hovering, arrows are hidden.
  - On hover, the arrow buttons should turn white (full opacity). When not hovered (but section is hovered), arrows should be faded/dim.
  - Apply the same gradient icon colorization described above to the 3 new cards as well.

---

## DASHBOARD — LINK INPUT AREA

- [x] The "Get Clips" button on the right side of the link input should have a white background BY DEFAULT. Currently it only turns white after a link is pasted — change the default state to match the post-paste appearance.
- [x] When a link is pasted into the input:
  - The "Get Clips" button should grow by 10%.
  - An animated RGB border (purple/violet tones) should appear around it — styled like a snake chasing its own tail (the tail follows the head around the border in a looping animation).
  - The animation should NOT be linear. Use an ease-in-out or custom cubic-bezier curve for a smooth, polished feel.
- [x] Add floating bubble animations rising from the bottom of the upload box upward. These bubbles should:
  - Be small, white, and semi-transparent.
  - Contain random words like "Podcast", "Gaming", "Interview", etc.
  - As they rise, they should slowly shrink and fade out (scale down + fade out).
  - Add subtle liveliness to the background without interfering with user interaction (use pointer-events: none).

---

## DASHBOARD — RECENT PROJECTS

- [x] Video previews are not showing in the Recent Projects section — it's showing a plain dark grey instead of the actual video thumbnail. Fix this so thumbnails display correctly, exactly as they do in the Projects page. Do not change the card design, only fix the preview/thumbnail rendering.

---

## DASHBOARD — LAYOUT & SPACING

- [x] The dashboard content ("Powered by AI" section and "Recent Projects") is currently centered with padding on both sides. Remove this padding — the content should stretch to full width. When the sidebar is open, the right side should shrink accordingly. When the sidebar is closed, it should expand back. Plan this carefully to ensure no buttons shift position or cause any UI/UX layout issues.

---

## SETTINGS PAGE

- [x] The settings sidebar currently has no padding/spacing between menu item names. Fix this so the spacing matches the main sidebar exactly.
- [x] Apply the same #faf9f5 white text color to all settings sidebar text items (same fix as the main sidebar).
- [x] In the settings sidebar, hovering over a menu item currently shows no visual change. Fix this: hovering should show the same background highlight that appears on click — same style, same behavior as in the main sidebar.

---

## FAVICON & LOGO

- [x] Replace the favicon on clip.prognot.com and prognot.com with the image file named "prognot-favicon" located in the documents folder. The image has a transparent background — use it as-is.
- [x] In the main sidebar, there is a logo to the left of the "Prognot" text at the top. Replace this logo with the same "prognot-favicon" image. Transparent background, no modifications.

---

## DASHBOARD — JOB PROCESSING FLOW

- [x] Currently, after the user uploads a video and starts processing, they remain on the same screen and watch the transcription/analysis progress ("Transcript received", "Analyzing with AI", etc.). Change this behavior: as soon as the user starts a job, immediately redirect them back to the dashboard. The job will already be visible in the "Active Jobs" section, which reassures the user that processing is underway. The user should not feel like they need to stay on the page.

---

## SYSTEM-WIDE — TOAST NOTIFICATIONS

- [x] Implement a toast notification system across the entire application.
  - Success actions → green-toned "Success" toasts.
  - Error actions (e.g. invalid link, file too large) → red-toned "Error" toasts.
  - Use a modern library standard such as `sonner` or `react-hot-toast`.
  - Toasts should appear in the bottom-right or top-center of the screen and auto-dismiss after 3–4 seconds.
  - Create a dedicated folder or file for toast configuration so it's easy to find and extend later. All future error/success messages across the app should use this same system.
  - The system should be built generically — even if I add new constraints or error conditions later, they will automatically plug into this notification system.
