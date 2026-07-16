# 🏗️ Crane Tracker — MVP Product Specification

**Version 0.3 · Draft**

---

## Overview

Crane Tracker is a community-driven map for construction crane enthusiasts. Anyone can pin a crane they spot, upload photos, and link to news articles about the construction site — no account required. The map shows cranes as active or historical, building a living archive of urban development.

| | |
|---|---|
| **Target users** | Crane hobbyists and spotters |
| **Submission model** | Anonymous, open — no accounts required |
| **Primary interaction** | Map-first: tap to place a pin, upload photos, add metadata |
| **Status tracking** | Active (crane is up) vs. Gone (crane removed) |
| **Hosting philosophy** | Minimize cost; free-tier services wherever possible |

---

## Feature Scope

| Feature | Description | MVP | Later |
|---|---|:---:|:---:|
| Interactive map | Leaflet.js + OpenStreetMap tiles, full-screen map view | ✅ | |
| Color-coded pins | Green = Active, Gray = Gone | ✅ | |
| Pin crane | Tap map to drop a pin, drag to adjust location | ✅ | |
| Photo upload | Up to 3 photos per crane, stored in Supabase Storage | ✅ | |
| Crane metadata | Project name, crane type (dropdown), optional notes | ✅ | |
| Article links | Up to 3 URLs linking to news or project pages | ✅ | |
| Active / Gone status | Community "Report as gone" button, flips after threshold | ✅ | |
| Detail panel | Slide-in panel with photo carousel, links, metadata | ✅ | |
| Success feedback | Toast notification on successful submission | ✅ | |
| Rate limiting | IP-based submission throttle via Supabase Edge Function | ✅ | |
| Image compression | Client-side compression before upload (browser-image-compression) | ✅ | |
| Activity feed | Reverse-chronological feed of newly added cranes with infinite scroll | | ✅ |
| Stats overview | Standalone /stats page with crane counts, hotspots, and city leaderboard | | ✅ |
| User accounts | Login, profiles, attribution | | ✅ |
| Comments / discussion | Per-crane comment threads | | ✅ |
| Push notifications | Alerts for new cranes near a saved location | | ✅ |
| Specs database | Crane manufacturer, model, height, capacity fields | | ✅ |
| Mobile app | Native iOS / Android | | ✅ |
| Duplicate detection | Warn if a pin is placed near an existing crane | | ✅ |

---

## UX Flow

### Viewing the Map

- Full-screen Leaflet map loads with all cranes pinned on initial render
- Green pins = Active cranes, gray pins = Gone cranes
- Tapping a pin opens the Crane Detail Panel

### Crane Detail Panel (Read Mode)

- Photo carousel (swipeable if multiple photos)
- Project name, crane type, date first spotted
- Article links rendered as clickable URLs
- "Report as Gone" button — records reporter IP; status flips after 3 reports

### Adding a Crane (Submission Flow)

1. User taps the `+` button or taps an empty spot on the map
2. A draggable temporary pin drops at that location with tooltip: *"Adding crane here — drag to adjust"*
3. Submission panel slides in from the right (desktop) or bottom sheet on mobile
4. User fills in photos + optional metadata and hits Submit
5. Photos upload to Supabase Storage → URLs saved to Postgres → pin goes live
6. Panel closes, map animates to new pin, success toast appears

### Mobile Behavior

- Bottom sheet replaces side panel on small screens
- File input uses `capture="environment"` to open camera directly
- All tap targets minimum 44×44px

---

## Data Model

### `cranes`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | Auto-generated |
| `lat` | `float8` | Latitude of pin |
| `lng` | `float8` | Longitude of pin |
| `name` | `text` (nullable) | User-supplied nickname |
| `project_name` | `text` (nullable) | Construction project name |
| `crane_type` | `text` | `tower \| mobile \| crawler \| unknown` |
| `status` | `text` | `active \| gone` — defaults to `active` |
| `notes` | `text` (nullable) | Free-text notes from submitter |
| `created_at` | `timestamptz` | Submission timestamp |
| `updated_at` | `timestamptz` | Last status change |

### `crane_photos`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `crane_id` | `uuid` FK → cranes | |
| `storage_url` | `text` | Full public URL from Supabase Storage |
| `uploaded_at` | `timestamptz` | |

### `crane_links`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `crane_id` | `uuid` FK → cranes | |
| `url` | `text` | Article or project page URL |
| `title` | `text` (nullable) | Optional display label |

### `gone_reports`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `crane_id` | `uuid` FK → cranes | |
| `reporter_ip` | `text` | Hashed IP of reporter |
| `created_at` | `timestamptz` | |

> When `gone_reports` count for a crane reaches 3, an Edge Function flips `cranes.status = 'gone'` and sets `updated_at`.

---

## Architecture

### Stack

| | |
|---|---|
| **Frontend** | React + Leaflet.js — hosted on Vercel (free) |
| **Database** | Supabase Postgres (managed, free tier: 500 MB) |
| **REST API** | Supabase PostgREST — auto-generated, no custom backend needed |
| **File storage** | Supabase Storage (free tier: 1 GB) — public bucket |
| **Custom logic** | Supabase Edge Functions (Deno/TypeScript) for gone-report threshold and rate limiting |
| **Map tiles** | OpenStreetMap via Leaflet.js (free, no API key) |

### Request Flow

```
User's Browser (React)
        │
        ├──[load cranes]────► Supabase REST API ──► Postgres
        │
        ├──[upload photo]───► Supabase Storage
        │
        ├──[submit crane]───► Supabase REST API ──► Postgres
        │                     (inserts crane + photo URLs + links)
        │
        └──[report gone]────► Supabase Edge Function
                              → checks report count
                              → updates status if threshold met
```

### Row-Level Security (RLS) Policies

| Operation | Who |
|---|---|
| `SELECT` | Public — anyone can read cranes, photos, links |
| `INSERT` | Public — anonymous submissions allowed |
| `UPDATE` / `DELETE` | `service_role` only — Edge Functions mutate status |

### Edge Functions

| Function | Responsibility |
|---|---|
| `handle-gone-report` | Receives `crane_id` + hashed IP. Inserts to `gone_reports`. Checks count — if ≥ 3, updates `cranes.status = 'gone'`. |
| `rate-limit-submission` | Checks submission frequency by hashed IP. Rejects if > 5 submissions per hour. |
| `process-photo` *(optional)* | Resize/compress image server-side before storing. Useful if client-side compression is insufficient. |

---

## Photo Storage

### Bucket Structure

A single public Supabase Storage bucket named `crane-photos`. Files organized by crane ID:

```
crane-photos/
  {crane_id}/
    {timestamp}-{filename}.jpg
    {timestamp}-{filename}.jpg
  {crane_id}/
    ...
```

### Upload Pipeline

1. User selects file(s) on device (up to 3, max 5 MB each)
2. Client-side compression via `browser-image-compression` (target: < 800 KB per photo)
3. Upload to Supabase Storage, receive storage path
4. Construct public URL from path
5. Save URL to `crane_photos` table alongside crane record

### Storage Limits

At 500 KB average per compressed photo, the 1 GB free tier supports roughly 2,000 photos — a comfortable runway for early growth. Supabase Storage beyond the free tier costs approximately $0.021/GB.

---

## Spam & Abuse Mitigation

Given fully anonymous submissions, lightweight protections are applied at the Edge Function layer:

| Mechanism | Detail |
|---|---|
| IP rate limiting | Max 5 crane submissions per IP per hour |
| File size cap | 5 MB per photo, enforced client-side before upload attempt |
| Honeypot field | Hidden form field — any submission with it filled is silently dropped |
| Report threshold | Gone reports require 3 unique IPs to prevent single-user manipulation |
| Soft delete flag | `report_inappropriate` flag per crane; admin can soft-delete at threshold |
| URL validation | Basic format check on article links (no live fetching) |

---

## Frontend Component Map

```
<App>
  <MapView>               ← Leaflet map, full screen
    <CranePin />          ← per crane, color coded active/gone
    <TempPin />           ← draggable, shown during submission
  </MapView>

  <CraneDetailPanel>      ← slides in on pin click (read mode)
    <PhotoCarousel />
    <LinkList />
    <ReportGoneButton />
  </CraneDetailPanel>

  <SubmissionPanel>       ← slides in on map click (write mode)
    <PhotoUploader />     ← drag/drop + preview thumbnails
    <CraneForm />         ← project name, type, links, notes
    <SubmitButton />
  </SubmissionPanel>

  <Toast />               ← success/error feedback
</App>
```

| Component | Role | Notes |
|---|---|---|
| `<App />` | Root | Holds map state, selected crane, submission mode |
| `<MapView />` | Map container | Leaflet map, renders all CranePin children |
| `<CranePin />` | Per-crane marker | Color by status; click opens CraneDetailPanel |
| `<TempPin />` | Placement marker | Draggable pin shown during submission flow |
| `<CraneDetailPanel />` | Read panel | Photo carousel, metadata, links, ReportGoneButton |
| `<SubmissionPanel />` | Write panel | PhotoUploader + CraneForm + SubmitButton |
| `<PhotoUploader />` | Photo input | Drag/drop + preview thumbnails; triggers compression |
| `<CraneForm />` | Metadata form | Project name, type dropdown, links, notes |
| `<Toast />` | Feedback | Success / error notification, auto-dismisses |

---

## Cost Estimate

| Service | What it covers | Free tier | Est. cost at scale |
|---|---|---|---|
| Vercel | Frontend hosting, CDN | Free (Hobby plan) | ~$0/mo for low traffic |
| Supabase Postgres | Database | Free (500 MB) | ~$25/mo (Pro) when needed |
| Supabase Storage | Photo storage | Free (1 GB) | $0.021/GB overage |
| Supabase Edge Functions | Rate limiting, gone logic | Free (500K invocations) | Negligible |
| OpenStreetMap | Map tiles | Free | Free |
| Domain (.com) | Custom domain | — | ~$12/yr |

**Total estimated cost at MVP scale: ~$1/month** (domain amortized).

> ⚠️ Supabase pauses inactive free-tier projects after 1 week of inactivity. Mitigate with a free cron ping service (e.g. [cron-job.org](https://cron-job.org)) until traffic is self-sustaining.

---

## Feature Spike: Activity Feed

A reverse-chronological feed of cranes as they are added to the map — a second way to explore the data beyond the map itself.

### Page Structure

The feed lives at `/feed` as a dedicated page, separate from the map view. Each feed entry links back to the map, flying to and opening that crane's detail panel (e.g. `/?crane={id}`). A persistent nav bar connects the two views.

### Feed Entry Card

Each card shows:

- **Thumbnail** — first photo for the crane, or a placeholder icon if none uploaded
- **Project name / nickname** — falls back to crane type + location if unnamed
- **Location** — city or neighborhood, derived from reverse geocoding `lat/lng` at submission time (see note below)
- **Date added** — relative time (e.g. "3 days ago"), full date on hover
- **Status badge** — Active or Gone, color-coded

Clicking anywhere on the card navigates to `/?crane={id}`, centering the map on that pin and opening the detail panel.

### Filtering

A filter bar sits above the feed with a single toggle:

| Filter | Options |
|---|---|
| Status | All · Active only · Gone only |

The filter updates the feed in place without a page reload. No crane-type filter in this iteration.

### Infinite Scroll

- Initial load fetches 20 entries ordered by `cranes.created_at DESC`
- As the user scrolls to the bottom, the next 20 are fetched (`offset`-based pagination against the Supabase REST API)
- A subtle loading spinner appears at the bottom during fetch
- When all entries are exhausted, a "You've seen them all" end-of-feed message is shown

### Location Derivation

Crane submissions capture `lat/lng` but not a human-readable location string. Two options:

| Approach | Tradeoff |
|---|---|
| Reverse geocode at submission time (Nominatim/OSM, free) | Store city/neighborhood in a `location_label` column on `cranes`; no per-request cost at read time |
| Reverse geocode at read time | Simpler schema, but adds latency and hammers a free API on every feed load |

**Recommended:** reverse geocode once at submission time, store result in a `location_label text` column. Add this column to the `cranes` table.

### Data Model Addition

Add one column to `cranes`:

| Column | Type | Notes |
|---|---|---|
| `location_label` | `text` (nullable) | Human-readable city/neighborhood, derived at submission time via Nominatim reverse geocode |

### Component Additions

```
<FeedPage>
  <FeedFilterBar />        ← status toggle (All / Active / Gone)
  <FeedList>
    <FeedCard />           ← thumbnail, name, location, date, status badge
    <FeedCard />
    ...
    <InfiniteScrollSentinel />  ← triggers next page fetch when visible
  </FeedList>
  <EndOfFeedMessage />
</FeedPage>
```

---

## Feature Spike: Stats Overview Page

A standalone `/stats` page giving a bird's-eye view of the Crane Tracker dataset — how many cranes, where they're concentrated, and what's been happening recently.

### Page Structure

Three sections stacked vertically on a single scrollable page:

1. **Headline numbers** — quick at-a-glance stats across the top
2. **City leaderboard** — ranked list of most active cities
3. **Construction hotspots** — clusters of high crane density

A "Last updated" timestamp at the top indicates when the stats were last computed.

### Section 1: Headline Numbers

Four stat cards displayed in a row (2×2 grid on mobile):

| Stat | Definition |
|---|---|
| Total cranes tracked | Count of all cranes ever added |
| Currently active | Count where `status = 'active'` |
| Added in last 30 days | Count where `created_at >= now() - interval '30 days'` |
| Cities represented | Count of distinct `location_label` city values |

Each card shows the number large, with a short label beneath it. No charts — clean and fast to scan.

### Section 2: City Leaderboard

A ranked list of the top 10 cities by active crane count, displayed as a leaderboard table:

| Rank | City | Active cranes | Total ever tracked |
|---|---|---|---|
| 🥇 1 | New York, NY | 42 | 61 |
| 2 | Seattle, WA | 38 | 45 |
| ... | ... | ... | ... |

- Sorted by active crane count descending by default
- Each city name links to the map view pre-filtered to that city (`/?city=Seattle`)
- Top 3 ranks get medal emojis; ranks 4–10 are plain numbers
- "Total ever tracked" gives a sense of historical construction activity vs. current

### Section 3: Construction Hotspots

A list of the top 5 geographic clusters — areas with the highest density of cranes within a ~1 km radius of each other. Each hotspot entry shows:

- A descriptive label (e.g. "Downtown Seattle", derived from the centroid's reverse geocode)
- Active crane count in the cluster
- A "View on map" link that flies the map to that location

**How clusters are computed:** Hotspots are pre-computed rather than calculated on every page load. A scheduled job (Supabase cron via `pg_cron`, or an external cron ping) runs nightly and writes results to a `stats_cache` table. The `/stats` page reads from this cache rather than running expensive aggregation queries live.

### Data Model Addition

A `stats_cache` table stores pre-computed results:

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `key` | `text` | Identifier e.g. `city_leaderboard`, `hotspots`, `headline_counts` |
| `value` | `jsonb` | Computed result as JSON blob |
| `computed_at` | `timestamptz` | When this cache entry was last refreshed |

This keeps the `/stats` page fast — every query is a simple `SELECT value FROM stats_cache WHERE key = '...'` — and avoids putting expensive aggregation load on the free-tier Postgres instance.

### Cluster Detection Approach

Hotspot clustering can be done two ways:

| Approach | Tradeoff |
|---|---|
| Simple grid bucketing (round lat/lng to ~1km grid squares, count per cell) | Easy to implement in SQL, good enough for MVP-adjacent use |
| PostGIS `ST_ClusterDBSCAN` | More accurate geographic clustering, requires PostGIS extension |

**Recommended:** Start with grid bucketing — it's a few lines of SQL and runs fine as a nightly job. PostGIS is a natural upgrade if cluster accuracy becomes important.

### Caching Strategy

Stats are computed nightly via a cron job. This means:
- Numbers may be up to 24 hours stale — acceptable for a hobby site
- The "Last updated" timestamp on the page sets expectations
- No live aggregation queries hit Postgres during page load

If real-time stats become desirable later, Supabase's Postgres functions could be called on demand with results cached in memory for a short TTL.

### Component Additions

```
<StatsPage>
  <LastUpdatedBanner />         ← "Stats last updated 3 hours ago"
  <HeadlineStats>
    <StatCard />                ← Total cranes
    <StatCard />                ← Currently active
    <StatCard />                ← Added last 30 days
    <StatCard />                ← Cities represented
  </HeadlineStats>
  <CityLeaderboard />           ← Ranked table, top 10 cities
  <HotspotList />               ← Top 5 clusters with "View on map" links
</StatsPage>
```

---

## Out of Scope for MVP

- User accounts, profiles, or attribution
- Comments or per-crane discussion threads
- Push notifications or location-based alerts
- Crane manufacturer / specs database
- Native mobile app (iOS / Android)
- Duplicate crane detection
- Admin dashboard or moderation UI
- Internationalization / localization
