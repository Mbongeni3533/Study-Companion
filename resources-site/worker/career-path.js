/* Builds the /api/resources/career-path payload.
 *
 * The page sends a field, one or more regions and a performance band. Local
 * opportunities come from the field's full list filtered to the chosen regions
 * (continental "africa" listings always stay in), boards from the union of the
 * chosen regions, and the advisor from the field and band. Ordering is the
 * dataset order, which is what the cards were authored in.
 */

import { careerPath } from "./career-path-data.js";

const FIELD_LABELS = Object.fromEntries(careerPath.fields.map((field) => [field.key, field.label]));

const REGION_LABELS = Object.fromEntries(careerPath.regions.map((region) => [region.key, region.label]));

function joinLocations(labels) {
  if (labels.length <= 1) return labels[0] || "";
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

export function careerPathResponse(params) {
  // Unknown values are a caller bug, not something to paper over with defaults.
  const unknownField = params.has("field") && !FIELD_LABELS[params.get("field")];
  const unknownRegion = params.getAll("region").some((key) => !REGION_LABELS[key]);
  const unknownBand = params.has("performance") && !careerPath.performance_bands.some((band) => band.key === params.get("performance"));
  if (unknownField || unknownRegion || unknownBand) return null;

  const fieldKey = params.get("field") || careerPath.default_field;
  const entry = careerPath.by_field[fieldKey];

  const requested = params.getAll("region").filter((key) => REGION_LABELS[key]);
  const regions = requested.length ? [...new Set(requested)] : [careerPath.default_region];

  const performance = params.get("performance") || careerPath.default_performance;

  const allowed = new Set([...regions, "africa"]);
  const local = entry.local.filter((item) => allowed.has(item.region));

  const boardNames = new Set();
  regions.forEach((region) => (entry.board_regions[region] || []).forEach((name) => boardNames.add(name)));
  const boards = entry.boards.filter((board) => boardNames.has(board.name));

  const gaps = regions.map((region) => entry.gaps[region]).filter(Boolean);

  return {
    fields: careerPath.fields,
    regions: careerPath.regions,
    region_groups: careerPath.region_groups,
    selected: {
      field: fieldKey,
      field_label: FIELD_LABELS[fieldKey],
      region: regions[0],
      region_label: REGION_LABELS[regions[0]],
      regions: regions.map((key) => ({ key, label: REGION_LABELS[key] })),
      locations_label: joinLocations(regions.map((key) => REGION_LABELS[key])),
    },
    profile: entry.profile,
    local,
    abroad: entry.abroad,
    funding: entry.funding,
    boards,
    gaps,
    performance_bands: careerPath.performance_bands,
    advisor: entry.advisor[performance],
    counts: { local: local.length, abroad: entry.abroad.length, funding: entry.funding.length },
    coverage: careerPath.coverage,
  };
}
