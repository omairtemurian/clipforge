import type { BrollSource, BrollSpot, StockClip, TrackItem } from "@/api/types";

/** The B-roll item that plays during spot (it overlaps the spot's time),
 * if there is one; a result chosen for the spot then replaces it. */
export function placedAt(
  items: TrackItem[],
  spot: Pick<BrollSpot, "start" | "end">,
): TrackItem | undefined {
  return items.find((item) => item.start < spot.end && item.end > spot.start);
}

/** The shape of B-roll: a full-screen cutaway or a picture-in-picture. */
export function brollMode(item: TrackItem): "cutaway" | "pip" {
  return item.props.mode === "pip" ? "pip" : "cutaway";
}

/** What a stock video becomes: the body that PUT /broll/{item} takes. */
export function stockSource(stock: StockClip): BrollSource {
  return { stock, asset_id: null };
}
