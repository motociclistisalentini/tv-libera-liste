#!/usr/bin/env python3
"""Aggrega stream pubblici per TV Libera. La disponibilità e i diritti non sono garantiti."""
import json, re, unicodedata, urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCES=[
 ("TvIt","https://tvit.leicaflorianrobert.dev/iptv/list.m3u"),
 ("IPTV-Italy","https://raw.githubusercontent.com/sfiorini/IPTV-Italy/main/iptvitaly.m3u"),
 ("IPTV-org Italia","https://iptv-org.github.io/iptv/countries/it.m3u"),
]
EPGS=[
 "https://tvit.leicaflorianrobert.dev/epg/list.xml",
 "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz",
]
ATTR=re.compile(r'([\w-]+)="([^"]*)"')

def load(url):
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (TVLiberaPlaylist/1.0)"})
    with urllib.request.urlopen(request,timeout=35) as response:
        return response.read(12_000_000).decode("utf-8-sig",errors="replace")

def key_name(name):
    s=unicodedata.normalize("NFKD",name).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\s*(?:\[alternativa\s*\d+\]|\b(?:hd|fhd|sd|uhd|4k)\b)"," ",s)
    return re.sub(r"[^a-z0-9]+","",s)

def parse(body,source):
    item=None
    for raw in body.splitlines():
        s=raw.strip()
        if s.startswith("#EXTINF:"):
            info,_,name=s.partition(",")
            a=dict(ATTR.findall(info))
            item={"name":name.strip() or a.get("tvg-name",""),"id":a.get("tvg-id",""),
                  "logo":a.get("tvg-logo",""),"group":a.get("group-title","TV Italia"),
                  "number":a.get("tvg-chno",""),"source":source,"options":[]}
        elif s.startswith("#EXTVLCOPT:") and item:
            item["options"].append(s)
        elif s and not s.startswith("#") and item:
            if s.startswith(("https://","http://")):
                item["url"]=s
                yield item
            item=None

def clean(s):
    return str(s or "").replace('"',"").replace("\n"," ").replace("\r"," ")

def main():
    grouped=OrderedDict()
    status=[]
    successful=0
    for source,url in SOURCES:
        try:
            entries=list(parse(load(url),source))
            if not entries:
                raise ValueError("Playlist vuota")
            successful+=1
            status.append({"source":source,"ok":True,"entries":len(entries)})
        except Exception as exc:
            status.append({"source":source,"ok":False,"error":str(exc)[:180]})
            continue
        for e in entries:
            k=key_name(e["name"])
            if not k: continue
            g=grouped.setdefault(k,{"name":e["name"],"id":e["id"],"logo":e["logo"],
                "group":e["group"],"number":e["number"],"streams":[]})
            for dst,src in (("id","id"),("logo","logo"),("number","number")):
                if not g[dst] and e[src]: g[dst]=e[src]
            if e["url"] not in {s["url"] for s in g["streams"]}:
                g["streams"].append({"url":e["url"],"source":source,"options":e["options"]})
    if successful==0:
        raise SystemExit("Nessuna fonte disponibile: mantengo i file pubblicati in precedenza.")
    # Evita di sostituire una lista buona con un aggiornamento palesemente incompleto.
    if len(grouped)<20:
        raise SystemExit("Meno di 20 canali: aggiornamento annullato.")
    groups=sorted(grouped.values(),key=lambda g:(
        int(g["number"]) if str(g["number"]).isdigit() else 99999,g["name"].lower()))
    epg=";".join(EPGS)
    lines=[f'#EXTM3U url-tvg="{epg}" x-tvg-url="{epg}"']
    for g in groups:
        for i,stream in enumerate(g["streams"]):
            name=g["name"] if i==0 else f'{g["name"]} [alternativa {i}]'
            lines.append('#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" tvg-chno="%s" group-title="%s",%s' % (
                clean(g["id"]),clean(g["name"]),clean(g["logo"]),clean(g["number"]),
                clean(g["group"]),clean(name)))
            lines.extend(stream["options"])
            lines.append(stream["url"])
    (ROOT/"TV_LIBERA_AUTO_EPG.m3u").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (ROOT/"canali_fallback.json").write_text(json.dumps({
        "updated_utc":datetime.now(timezone.utc).isoformat(),"epg":EPGS,"channels":groups
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (ROOT/"stato_aggiornamento.json").write_text(json.dumps({
        "updated_utc":datetime.now(timezone.utc).isoformat(),"sources":status,
        "channels":len(groups),"streams":sum(len(g["streams"]) for g in groups)
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Canali:",len(groups),"Flussi:",sum(len(g["streams"]) for g in groups))

if __name__=="__main__":
    main()
