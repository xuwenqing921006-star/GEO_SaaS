# T-014 Business Blocker Remediation

Date: 2026-07-28  
Role: Developer  
Status: ready for independent review; Developer does not mark PASS

## PA-01 — channel adaptation loop

- Newly generated strategy briefs contain operator-publishable suggested
  channels instead of an empty list.
- A completed P06 recommendation task writes its top four
  operator-publishable channel IDs back to every content brief.
- P05 shows the selected channel names and enables one-click generation of the
  corresponding channel variants.
- P05 maps each `channel_id` to its own version, then displays its platform
  name, title, body preview, quality status and independent Markdown/DOCX
  export actions.
- Any named channel product can be selected into the editor. Its title and body
  can be adjusted after AI generation, and saving creates a new checked version
  while updating only that channel's latest-version mapping.
- Titles and bodies pass the same deterministic and independent-model quality
  checks. Toutiao receives a deterministic user-question title and no timed
  speed-reading claim.
- Channel recommendation jobs lock the target brief rows before writeback.
  Exports identify the exact adapted channel and distinguish generation-time
  from current channel recommendations.
- Zhihu, Sohu and Toutiao variants are structurally distinct and remain
  exportable after the quality gate. The Toutiao fast-summary wording no longer
  invents an unsupported numeric claim.

Developer verification:

- strategy, channels and content backend tests passed;
- T010 real-browser content journey passed, including separate Zhihu and
  Toutiao downloads whose files contain distinct titles and exact channel IDs,
  plus selecting and editing a non-last Zhihu product;
- T011 real-browser channel-recommendation journey passed;
- the complete 11-journey real Chromium suite passed.

## PA-02 — P1 manual monitoring

- P07 selects all 10 active P0 and P1 target platforms by default.
- The operator can switch between all platforms, P0 only, or individual
  platforms before creating a batch.
- Manual-monitoring samples are created for Quark, WeChat, Douyin and Nami, as
  well as Doubao, DeepSeek, Qwen, Yuanbao, Kimi and Baidu AI Search.
- The platform catalog exposes official entries and makes the manual/API
  boundary explicit; the product does not claim unsupported automated
  collection.

Developer verification:

- monitoring backend tests passed;
- T012 real-browser monitoring journey passed with 10 platform groups and more
  than 42 samples, a successful Quark consumer sample, a failed WeChat consumer
  sample with its reason, and a Web assertion that one failure does not enlarge
  the one-effective-sample metric denominator;
- the complete 11-journey real Chromium suite passed.

## Final developer gates after remediation

- `pnpm check`: PASS (frontend 40/40; backend 150 passed, 5
  environment-gated skips; format, lint, typecheck, build and Compose config
  passed).
- Backend statement coverage: 84.83% in the independent isolated rerun (gate
  75%; the Developer run reported 84.86%, so the lower reproducible value is
  retained).
- Core branch coverage: 88.27% (gate 85%).
- Six final images: 0 Critical and 0 High known vulnerabilities.
- Production drill: all six recovery, monitoring and HTTPS assertions passed;
  the temporary stack was removed.
- Existing customer PostgreSQL data and configured provider keys were not
  changed.
