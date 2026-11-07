#!/usr/bin/env python3
"""TV Libera: playlist pubbliche, loghi, EPG XMLTV e flussi alternativi."""
import gzip
import io
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ("TvIt", "https://tvit.leicaflorianrobert.dev/iptv/list.m3u"),
    ("IPTV-Italy", "https://raw.githubusercontent.com/sfiorini/IPTV-Italy/main/iptvitaly.m3u"),
    ("IPTV-org Italia", "https://iptv-org.github.io/iptv/countries/it.m3u"),
]
EPGS = [
    "https://tvit.leicaflorianrobert.dev/epg/list.xml",
    "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz",
]
ATTR = re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')
BAD_HOSTS = {"team-tv.co"}  # Non includere relay non ufficiali palesemente sospetti.

def fetch(url, limit=60_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": "TVLibera/1.0 (public-metadata)"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read(limit)

def norm(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\[[^\]]*\]|\([^)]*(?:p|hd|sd|italy|not 24/7|geo-blocked)[^)]*\)", " ", value)
    value = re.sub(r"\b(?:hd|fhd|sd|uhd|4k|italy|italia|geo blocked)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)

def split_info(info):
    # Una virgola presente dentro una stringa quotata non termina #EXTINF.
    quoted = False
    for index, char in enumerate(info):
        if char == '"':
            quoted = not quoted
        elif char == ',' and not quoted:
            return info[:index], info[index + 1:]
    return info, ""

def parse(body, source):
    item = None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            info, name = split_info(line)
            attrs = dict(ATTR.findall(info))
            item = dict(name=name.strip() or attrs.get("tvg-name", ""),
                        id=attrs.get("tvg-id", ""),
                        logo=attrs.get("tvg-logo", ""),
                        group=attrs.get("group-title", "TV Italia"),
                        number=attrs.get("tvg-chno", ""),
                        source=source, options=[])
        elif line.startswith("#EXTVLCOPT:") and item:
            item["options"].append(line)
        elif line and not line.startswith("#") and item:
            if line.startswith(("http://", "https://")) and urlparse(line).hostname not in BAD_HOSTS:
                item["url"] = line
                yield item
            item = None

def load_epg():
    ids, by_name, epg_status = set(), {}, []
    for url in EPGS:
        try:
            data = fetch(url)
            if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            found = 0
            # Gestisce XMLTV grandi senza conservare i programmi nella RAM.
            for event, element in ET.iterparse(io.BytesIO(data), events=("end",)):
                if element.tag == "channel":
                    cid = element.attrib.get("id", "").strip()
                    if cid:
                        ids.add(cid)
                        names = [t.text for t in element.findall("display-name") if t.text]
                        names.append(cid.split("@")[0])
                        for name in names:
                            k = norm(name)
                            if k:
                                by_name.setdefault(k, cid)
                        found += 1
                    element.clear()
                elif element.tag == "programme":
                    element.clear()
            epg_status.append({"url": url, "ok": True, "channels": found})
        except Exception as exc:
            epg_status.append({"url": url, "ok": False, "error": str(exc)[:150]})
    return ids, by_name, epg_status

def value(text):
    return str(text or "").replace('"', "").replace("\n", " ").replace("\r", " ")

def main():
    groups = OrderedDict()
    sources_status = []
    successes = 0
    for source, url in SOURCES:
        try:
            entries = list(parse(fetch(url, 15_000_000).decode("utf-8-sig", errors="replace"), source))
            if not entries:
                raise ValueError("Playlist vuota")
            sources_status.append({"source": source, "ok": True, "entries": len(entries)})
            successes += 1
        except Exception as exc:
            sources_status.append({"source": source, "ok": False, "error": str(exc)[:150]})
            continue
        for entry in entries:
            k = norm(entry["name"])
            if not k:
                continue
            g = groups.setdefault(k, dict(name=entry["name"], id=entry["id"], logo=entry["logo"],
                                          group=entry["group"], number=entry["number"], streams=[]))
            for field in ("id", "logo", "number"):
                if not g[field] and entry[field]:
                    g[field] = entry[field]
            if entry["url"] not in {s["url"] for s in g["streams"]}:
                g["streams"].append(dict(url=entry["url"], source=source, options=entry["options"]))

    if not successes or len(groups) < 20:
        raise SystemExit("Aggiornamento annullato: fonti insufficienti, lista precedente conservata.")

    xml_ids, xml_names, epg_status = load_epg()
    # Nel caso le guide non siano raggiungibili, conserviamo i tvg-id originali.
    epg_matched = 0
    for group in groups.values():
        original_id = group["id"]
        candidates = [
            norm(group["name"]), norm(original_id.split("@")[0]),
            norm(re.sub(r"\s*\([^)]*\)", "", group["name"]))
        ]
        match = original_id if original_id in xml_ids else ""
        if not match:
            for candidate in candidates:
                if candidate in xml_names:
                    match = xml_names[candidate]
                    break
        if match:
            group["id"] = match
            epg_matched += 1
        group["epg_verified"] = bool(match)
        group["logo_present"] = bool(group["logo"])
    ordered = sorted(groups.values(), key=lambda g: (
        int(g["number"]) if str(g["number"]).isdigit() else 999999,
        g["name"].lower()
    ))
    epg = ";".join(EPGS)
    lines = [f'#EXTM3U url-tvg="{epg}" x-tvg-url="{epg}"']
    for group in ordered:
        for index, stream in enumerate(group["streams"]):
            name = group["name"] if not index else f'{group["name"]} [alternativa {index}]'
            lines.append('#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" tvg-chno="%s" group-title="%s",%s' % (
                value(group["id"]), value(group["name"]), value(group["logo"]),
                value(group["number"]), value(group["group"]), value(name)))
            lines.extend(stream["options"])
            lines.append(stream["url"])
    (ROOT / "TV_LIBERA_AUTO_EPG.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "canali_fallback.json").write_text(json.dumps({
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "epg": EPGS, "channels": ordered,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources_status, "epg_sources": epg_status,
        "channels": len(ordered), "streams": sum(len(g["streams"]) for g in ordered),
        "logos_associated": sum(bool(g["logo"]) for g in ordered),
        "logos_missing": [g["name"] for g in ordered if not g["logo"]],
        "epg_matched": epg_matched,
        "epg_unmatched": len(ordered) - epg_matched,
    }
    (ROOT / "stato_aggiornamento.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("channels", "streams", "logos_associated", "epg_matched")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
