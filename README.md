# Best BiS Tooltip TBC (v2.5)

A World of Warcraft: The Burning Crusade Classic addon that shows BiS (Best in Slot) rankings directly in item tooltips.

## What it does

When you hover over an item, the addon adds a line to the tooltip showing its BiS status for your current spec and phase — so you always know if an item is worth picking up.

**Color coding:**
- 🟠 **Absolute BiS** — best item in slot
- 🟣 **BiS #2 / Close to BiS** — second or third best
- 🔵 **Sub-BiS (Optional)** — situational upgrade
- 🟢 **Sub-BiS Further Options** — minor upgrade

## Supported specs

All 23 TBC specs across all classes — Warriors, Paladins, Hunters, Rogues, Priests, Shamans, Mages, Warlocks, Druids.

## Phases

- Pre-Raid
- Phase 1 (Karazhan, Gruul, Magtheridon)
- Phase 2 (TK + SSC)

## Installation

1. Download the latest release
2. Extract to `World of Warcraft/_classic_tbc_/Interface/AddOns/`
3. Folder name must be: `Best BiS Tooltip TBC (v2.5)`
4. Enable the addon in-game

## Files

| File | Description |
|------|-------------|
| `Best BiS Tooltip TBC (v2.5).toc` | Addon manifest — tells WoW how to load the addon |
| `bisdata.lua` | BiS item database — all item IDs mapped to specs and phases |
| `main.lua` | Core logic — tooltip detection, color coding, spec detection |
