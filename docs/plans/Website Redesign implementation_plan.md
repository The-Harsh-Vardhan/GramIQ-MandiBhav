# Implementation Plan: Website Redesign

This plan covers redesigning the dynamic Next.js frontend to match the requested specifications:
1. Remove the announcement text `"Free daily mandi bhav reports — सोयाबीन · कपास — 4 भाषाओं में  | "` from the top banner, keeping only a premium styled RSS subscribe button/link.
2. Ensure the color scheme is Forest Green and Light Blue (already configured in `tailwind.config.ts` as `soil`, `field`, `grain`, `river`, `cloud`).
3. Add the logo at `web/public/logo.png` (from `assets/MandiBhav by GramIQ Logo.png`) in the navigation bar.
4. Ensure the favicon at `web/public/favicon.png` (from `assets/MandiBhav by GramIQ Favcon.png`) is linked correctly.
5. Replace the simple footer with a comprehensive, professional 3-column footer containing quick links, description, resources, and disclaimers.
6. Remove "Archive" / "Archived" terminology from the UI (changing it to "Reports", "Market Reports", etc.).

## Proposed Changes

### Components & Layout

#### [MODIFY] [site-shell.tsx](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/web/components/site-shell.tsx)
- Modify the announcement bar to remove the Hindi text and style it beautifully with a feed icon and "Subscribe to RSS Feed" text.
- Modify the navbar to replace the custom inline brand SVG with the logo image `/logo.png`.
- Rename navigation text `Archive` to `Reports`.
- Replace the basic 1-line footer with a professional 3-column dark green (`bg-soil`) footer.

### Pages

#### [MODIFY] [page.tsx](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/web/app/page.tsx)
- Modify search button text from "Explore archive" to "Search Reports".
- Adjust hover colors or minor spacing to align with the new header and footer.

#### [MODIFY] [page.tsx](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/web/app/archive/page.tsx)
- Rename page subtitle tag from "Archive" to "Market Reports".
- Rename page title from "Search the report ledger" to "Search Market Reports".
- Confirm date sorting functionality works as intended.

---

## Verification Plan

### Automated Tests
- Run `npm run build` inside the `web/` directory to ensure Next.js builds clean and there are no TypeScript compilation errors or typed routing issues.

### Manual Verification
- Deploy to Vercel and review the live layout.
- Verify that the logo, favicon, and announcement bar appear correctly.
- Verify that the footer links work as expected.
- Verify sorting works correctly by date.
