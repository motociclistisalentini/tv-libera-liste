# TV Libera — playlist italiana EPG e loghi

Indirizzo stabile da caricare in TV Libera:

https://raw.githubusercontent.com/motociclistisalentini/tv-libera-liste/main/TV_LIBERA_AUTO_EPG.m3u

La playlist si rigenera con GitHub Actions ogni 6 ore e quando cambia il generatore. Integra tre raccolte pubbliche, i loghi presenti nelle fonti e prova ad associare i tvg-id ai canali delle guide XMLTV disponibili.

## Altri file
- `stato_aggiornamento.json`: numero canali, flussi, EPG verificati e loghi mancanti
- `canali_fallback.json`: catalogo con gli URL alternativi, per eventuali lettori che supportino fallback
- `aggiorna.py`: codice di aggiornamento

**Nota:** un tvg-id non equivale alla garanzia di un programma EPG. La copertura dipende dalla guida e dal player. Flussi, loghi e diritti di ritrasmissione restano sotto controllo dei fornitori originari; verificarne le condizioni per usi commerciali.
