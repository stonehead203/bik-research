"""Bounded, resumable ETF checkpoints; only the OCI collector writes these rows."""
import copy
import hashlib
import json
from datetime import datetime, timezone

PROGRESS_KEY = "domestic-etf:progress:v2"
HOLDING_PREFIX = "domestic-etf:holding:v2:"
PROGRESS_FIELDS = (
    "asOf", "generatedAt", "enrichmentStatus", "enrichmentStage",
    "enrichmentProgress", "enrichmentCursor", "enrichmentUpdatedAt",
    "enrichmentError", "holdingsProvider", "scope", "changes", "trackingError",
)


def fingerprint(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def generation(payload):
    return str(payload.get("asOf") or "") + ":" + str(payload.get("generatedAt") or "")


class EtfCheckpointStore:
    def __init__(self, get, list_rows, upsert, upsert_rows, dashboard_key, stable_key):
        self.get = get
        self.list_rows = list_rows
        self.upsert = upsert
        self.upsert_rows = upsert_rows
        self.dashboard_key = dashboard_key
        self.stable_key = stable_key
        self.current_generation = None
        self.hashes = {}
        self.published_version = None

    def restore(self, snapshot):
        """Overlay durable per-ETF changes onto the initial snapshot after a restart."""
        if not isinstance(snapshot, dict) or not snapshot.get("asOf"):
            return snapshot
        result = copy.deepcopy(snapshot)
        self.current_generation = generation(snapshot) if snapshot.get("dataVersion") else None
        self.published_version = snapshot.get("dataVersion")
        progress = self.get(PROGRESS_KEY, None)
        if isinstance(progress, dict) and progress.get("generation") == self.current_generation:
            if progress.get("enrichmentStatus") == "collecting":
                for value in self.list_rows(HOLDING_PREFIX).values():
                    if value.get("generation") != self.current_generation:
                        continue
                    if value.get("checkpointAt", "") > progress.get("updatedAt", ""):
                        continue
                    ticker = value.get("ticker")
                    if ticker and isinstance(value.get("holding"), dict):
                        result.setdefault("holdingsByEtf", {})[ticker] = value["holding"]
                for key in PROGRESS_FIELDS:
                    if key in progress:
                        result[key] = copy.deepcopy(progress[key])
            self.published_version = progress.get("version") or snapshot.get("dataVersion")
        self.hashes = {k: fingerprint(v) for k, v in result.get("holdingsByEtf", {}).items()}
        return result

    def save(self, payload):
        """Publish at most an initial snapshot and a completed snapshot per generation.

        Intermediate checkpoints update only changed ETF rows and small progress.
        Advance local hashes only after every remote write succeeds, so retries
        remain idempotent. The public snapshot is never replaced by partial deltas.
        """
        clean = copy.deepcopy(payload)
        for key in ("loadedFrom", "_supabaseUpdatedAt", "servedFromLastGood", "activeCacheStatus", "dataVersion", "lastReadySavedAt"):
            clean.pop(key, None)
        gen = generation(clean)
        if gen != self.current_generation:
            initial = dict(clean)
            initial["dataVersion"] = fingerprint(clean)
            if not self.upsert(self.dashboard_key, initial):
                raise RuntimeError("ETF initial snapshot upload failed")
            self.current_generation = gen
            self.hashes = {k: fingerprint(v) for k, v in clean.get("holdingsByEtf", {}).items()}
            self.published_version = initial["dataVersion"]
            if clean.get("enrichmentStatus") == "ready":
                if not self.upsert(self.stable_key, initial):
                    self.current_generation = None
                    raise RuntimeError("ETF initial last-ready upload failed")

        next_hashes = {k: fingerprint(v) for k, v in clean.get("holdingsByEtf", {}).items()}
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {"key": HOLDING_PREFIX + ticker,
             "payload": {"generation": gen, "ticker": ticker, "holding": holding, "checkpointAt": now},
             "updated_at": now}
            for ticker, holding in clean.get("holdingsByEtf", {}).items()
            if self.hashes.get(ticker) != next_hashes[ticker]
        ]
        if rows and not self.upsert_rows(rows):
            raise RuntimeError("ETF delta checkpoint upload failed")

        complete = clean.get("enrichmentStatus") == "ready"
        version = fingerprint(clean) if complete else self.published_version
        if complete and version != self.published_version:
            clean["dataVersion"] = version
            if not self.upsert(self.dashboard_key, clean):
                raise RuntimeError("ETF completed snapshot upload failed")
            if not self.upsert(self.stable_key, clean):
                raise RuntimeError("ETF last-ready snapshot upload failed")

        progress = {key: clean.get(key) for key in PROGRESS_FIELDS}
        progress.update(generation=gen, version=version, collector="oci", updatedAt=now)
        if not self.upsert(PROGRESS_KEY, progress):
            raise RuntimeError("ETF progress upload failed")
        self.hashes = next_hashes
        self.published_version = version
        return True
