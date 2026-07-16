# Crane Tracker — Design Brief

## What it is

A community map where construction crane enthusiasts pin cranes they spot, upload photos, and track whether cranes are still active or gone. Think niche, hobbyist, lightweight — not a corporate SaaS product.

---

## Pages

- `/` — Full-screen interactive map (primary view)
- `/feed` — Reverse-chronological list of recently added cranes
- `/stats` — Overview page with headline numbers and city leaderboard

A persistent top nav connects all three.

---

## Map Page (Primary)

Full-screen map (Leaflet + OpenStreetMap). Two pin states:

- 🟢 **Active** — crane is up
- ⚫ **Gone** — crane has been removed

**Clicking a pin** → slide-in detail panel (right side desktop, bottom sheet mobile) showing:
- Photo carousel
- Project name, crane type, date spotted
- Article links
- "Report as Gone" button

**Adding a crane** → tap empty map area or `+` button → draggable temp pin drops → submission panel slides in with:
- Photo upload (up to 3, drag/drop or camera on mobile)
- Project name, crane type dropdown, optional notes, article links
- Submit button

---

## Feed Page (`/feed`)

Card-based list, newest first, infinite scroll. Each card shows:
- Photo thumbnail (or placeholder)
- Project name / nickname
- City / neighborhood
- Date added (relative, e.g. "3 days ago")
- Active / Gone status badge

Filter bar at top: **All · Active · Gone**

Each card links back to the map, flying to that crane's pin.

---

## Stats Page (`/stats`)

Three sections:

1. **Headline stat cards** (4 cards in a row): Total cranes tracked · Currently active · Added in last 30 days · Cities represented
2. **City leaderboard**: Ranked top 10 cities by active crane count, with "view on map" link per city
3. **Construction hotspots**: Top 5 geographic clusters with active crane count and "view on map" link

Numbers are pre-computed nightly — a "Last updated X hours ago" label sets expectations.

---

## Tone & Aesthetic

- **Audience**: hobbyists and enthusiasts — not construction professionals
- **Feel**: utilitarian but charming. Like a passion project with care put into it, not a startup landing page
- **Not**: corporate, data-heavy, cluttered
- Map is always the hero — everything else serves it

---

## Constraints

- Must work well on mobile (crane spotters submit from the field)
- No user accounts — fully anonymous
- Minimal chrome around the map on the main page
- Bottom sheet pattern on mobile for panels (not modals)
- Tap targets minimum 44×44px
