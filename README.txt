WAYBOUND — FRONTEND-ONLY PROJECT (FEATURE-ENHANCED)

This project uses plain HTML, CSS and Vanilla JavaScript. It does not require React, FastAPI, Python packages, a backend server or a database.

PROJECT FILES
- index.html: website structure and screens
- style.css: visual design and responsive layouts
- script.js: CSV loading, maps, search, filters, artisan stories, trip selections and local storage
- data/: tourism datasets and data documentation
- PHOTO_PREVIEW.html: image-reference preview page
- PHOTO_ATTRIBUTION_AND_SOURCES.csv: image source and attribution records
- PHOTO_RIGHTS_REVIEW.csv: image reuse/permission review notes

DATASET COUNTS
- destinations.csv: 46 destination records
- food.csv: 15 food records
- gi_products.csv: 40 GI product records
- crafts.csv: 20 craft records
- cultural_experiences.csv: 14 experience records
- media_assets.csv: 54 media rows; 45 destination IDs have image URL references
- sources_reference.csv: 323 source-reference rows

Image note: 45 destination IDs have image URL references, but not every image is cleared for public reuse. Check data/media_assets.csv and PHOTO_RIGHTS_REVIEW.csv for permission-required or representative images before public release. Image references are remote URLs, not downloaded files, and need internet access.

NEW FRONTEND FEATURES
1. Personalised interests: choose Nature, Heritage, Local Food, Traditional Crafts, Adventure and Village Experiences. Multiple interests work as OR filters. No interests are selected by default, so all curated destinations are visible until the visitor chooses filters. Preferences are saved in this browser.
2. Explore Nearby: search any Indian city/town/place using Photon; use the selected place as the centre for nearby curated AP/Telangana destinations. Quick radius options are available. The radius uses straight-line distance, not road distance.
3. Local Artisan Stories: story cards are generated from crafts.csv and connected to destinations/experiences where IDs are available. Materials, process, maker-community notes, products, history and source links are shown only where the data has values.

HOW THE NEW FEATURES USE DATA
- Artisan stories read crafts.csv and connect to cultural_experiences.csv through craft_id and destination_id.
- Interest matching reads destination descriptions/categories plus linked craft, food and cultural-experience records.
- Nearby discovery uses destination latitude/longitude from destinations.csv, plus the coordinates of the searched map location.

RUN THE WEBSITE (MAC / VS CODE)
1. Extract this project folder.
2. Open the Waybound_Seven_Photos folder in VS Code.
3. Keep the data folder next to index.html.
4. Install the VS Code Live Server extension if needed.
5. Right-click index.html and choose Open with Live Server.
6. A local address such as http://127.0.0.1:5500 should open.

Do not open index.html by double-clicking it as a file:// URL; browsers block CSV fetch() in that mode. A Python VS Code extension is not required.

FRONTEND-ONLY LIMITATIONS
- Trip selections are saved only in the current browser's localStorage. They are not shared with teammates or other visitors.
- Add a Place suggestions are saved only on the current device and are unverified. There is no admin approval in this frontend-only build.
- Interest matching is a keyword/data-link based filter, not a trained AI recommendation model.
- Straight-line distance is a Haversine estimate, not driving distance or travel time.
- External location search (Photon), OpenStreetMap map tiles and remote photos require internet access.

Before deployment, connect trip submissions and new-place suggestions to the backend your teammates develop, validate photo permissions, and verify opening times/prices with official sources.


PUTTAPAKA ADDED: DST-TG-0021 — Telia Rumal handloom-cluster discovery point in Yadadri Bhuvanagiri, Telangana. Linked to craft CRF-TG-0011, GI-0354 (Application 599), and cultural experience CEX-TG-0007. GI applicant address is officially tied to Puttapaka; the registered GI geographical area is Telangana. Workshop access and live demonstrations are not confirmed. Puttapaka currently has no cleared destination photograph.


PUTTAPAKA IMAGE ADDED
Puttapaka (DST-TG-0021) now has a Wikimedia Commons photo reference for a regional handloom-weaving scene. The source describes the photo as Pochampally Ikat handloom weaving in Mothkur, Yadadri Bhuvanagiri district, Telangana. It is a representative regional image, NOT a photo taken in Puttapaka and NOT specifically a Telia Rumal loom. Creator: Pranayraj1985. Licence: CC BY-SA 4.0. The image is hotlinked from Wikimedia Commons, not stored locally; internet is required. See PHOTO_ATTRIBUTION_AND_SOURCES.csv for required credit.


CRAFT TRAILS PAGE REMOVED
The separate Craft Trails navigation page and dedicated UI/code have been removed. The crafts.csv dataset is retained because Artisan Stories still uses it to display craft traditions, materials, processes, artisan-community information and source links.
