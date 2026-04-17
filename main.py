"""
IDX RS Score Threshold Calculator
==================================
Calculates the 7 percentile threshold values needed for the
RS Rating indicator in TradingView (Option B - Manual Input).

Run this script after market close (after 16:00 WIB) on any trading day.
Then paste the 7 output values into your TradingView indicator inputs.

Requirements:
    pip install yfinance pandas numpy tqdm

Usage:
    python idx_rs_thresholds.py
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import glob
import time
import datetime
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

OUTPUT_ROOT_DIR  = "outputs"
THRESHOLDS_DIR   = os.path.join(OUTPUT_ROOT_DIR, "thresholds")
DIAGNOSTICS_DIR  = os.path.join(OUTPUT_ROOT_DIR, "diagnostics")
RANKINGS_DIR     = os.path.join(OUTPUT_ROOT_DIR, "rankings")
HISTORY_DAYS     = 500   # calendar days — enough aligned bars for RS delta lookback
REQUEST_DELAY = float(os.environ.get("IDX_REQUEST_DELAY", REQUEST_DELAY))
MAX_WORKERS   = int(os.environ.get("IDX_MAX_WORKERS",   MAX_WORKERS))
MIN_TRADING_DAYS = 274   # minimum bars required; aligns with rs_delta (253 + 21)
IDX_TICKER       = "^JKSE"

# ── Data quality thresholds ────────────────────────────
MIN_PRICE        = 5.0   # IDR — skip stocks below this (penny stock / data artifact)
MAX_STALE_RATIO  = 0.20  # skip if >20% of bars have unchanged price (suspended/illiquid)
OUTLIER_FACTOR   = 5.0   # remove bars where price deviates >5x from 20-day rolling median
RS_SCORE_MIN     = 30.0  # discard RS Score below this (lost 70%+ vs IHSG — likely bad data)
# No upper cap — legitimate momentum stocks can score 300–600+

TOP_N_TERMINAL   = 10                       # stocks to print in terminal
FILE_RETENTION_KEEP = 30  # number of most recent output files to retain per directory

# Coverage warnings (percentile context)
WARN_COVERAGE_PCT = 45.0
WARN_MIN_SCORED   = 400


# ─────────────────────────────────────────────
# IDX STOCK UNIVERSE (956 stocks)
# Source: IDX official list — Daftar_Saham 26 March 2026
# Covers all boards: Utama, Pengembangan, Akselerasi,
#                    Pemantauan Khusus, Ekonomi Baru
# Stocks with insufficient price history are skipped automatically
# ─────────────────────────────────────────────

IDX_TICKERS = [
    "AALI.JK", "ABBA.JK", "ABDA.JK", "ABMM.JK", "ACES.JK",
    "ACST.JK", "ADES.JK", "ADHI.JK", "AISA.JK", "AKKU.JK",
    "AKPI.JK", "AKRA.JK", "AKSI.JK", "ALDO.JK", "ALKA.JK",
    "ALMI.JK", "ALTO.JK", "AMAG.JK", "AMFG.JK", "AMIN.JK",
    "AMRT.JK", "ANJT.JK", "ANTM.JK", "APEX.JK", "APIC.JK",
    "APII.JK", "APLI.JK", "APLN.JK", "ARGO.JK", "ARII.JK",
    "ARNA.JK", "ARTA.JK", "ARTI.JK", "ARTO.JK", "ASBI.JK",
    "ASDM.JK", "ASGR.JK", "ASII.JK", "ASJT.JK", "ASMI.JK",
    "ASRI.JK", "ASRM.JK", "ASSA.JK", "ATIC.JK", "AUTO.JK",
    "BABP.JK", "BACA.JK", "BAJA.JK", "BALI.JK", "BAPA.JK",
    "BATA.JK", "BAYU.JK", "BBCA.JK", "BBHI.JK", "BBKP.JK",
    "BBLD.JK", "BBMD.JK", "BBNI.JK", "BBRI.JK", "BBRM.JK",
    "BBTN.JK", "BBYB.JK", "BCAP.JK", "BCIC.JK", "BCIP.JK",
    "BDMN.JK", "BEKS.JK", "BEST.JK", "BFIN.JK", "BGTG.JK",
    "BHIT.JK", "BIKA.JK", "BIMA.JK", "BINA.JK", "BIPI.JK",
    "BIPP.JK", "BIRD.JK", "BISI.JK", "BJBR.JK", "BJTM.JK",
    "BKDP.JK", "BKSL.JK", "BKSW.JK", "BLTA.JK", "BLTZ.JK",
    "BMAS.JK", "BMRI.JK", "BMSR.JK", "BMTR.JK", "BNBA.JK",
    "BNBR.JK", "BNGA.JK", "BNII.JK", "BNLI.JK", "BOLT.JK",
    "BPFI.JK", "BPII.JK", "BRAM.JK", "BRMS.JK", "BRNA.JK",
    "BRPT.JK", "BSDE.JK", "BSIM.JK", "BSSR.JK", "BSWD.JK",
    "BTEK.JK", "BTEL.JK", "BTON.JK", "BTPN.JK", "BUDI.JK",
    "BUKK.JK", "BULL.JK", "BUMI.JK", "BUVA.JK", "BVIC.JK",
    "BWPT.JK", "BYAN.JK", "CANI.JK", "CASS.JK", "CEKA.JK",
    "CENT.JK", "CFIN.JK", "CINT.JK", "CITA.JK", "CLPI.JK",
    "CMNP.JK", "CMPP.JK", "CNKO.JK", "CNTX.JK", "COWL.JK",
    "CPIN.JK", "CPRO.JK", "CSAP.JK", "CTBN.JK", "CTRA.JK",
    "CTTH.JK", "DART.JK", "DEFI.JK", "DEWA.JK", "DGIK.JK",
    "DILD.JK", "DKFT.JK", "DLTA.JK", "DMAS.JK", "DNAR.JK",
    "DNET.JK", "DOID.JK", "DPNS.JK", "DSFI.JK", "DSNG.JK",
    "DSSA.JK", "DUTI.JK", "DVLA.JK", "DYAN.JK", "ECII.JK",
    "EKAD.JK", "ELSA.JK", "ELTY.JK", "EMDE.JK", "EMTK.JK",
    "ENRG.JK", "EPMT.JK", "ERAA.JK", "ERTX.JK", "ESSA.JK",
    "ESTI.JK", "ETWA.JK", "EXCL.JK", "FAST.JK", "FASW.JK",
    "FISH.JK", "FMII.JK", "FORU.JK", "FPNI.JK", "GAMA.JK",
    "GDST.JK", "GDYR.JK", "GEMA.JK", "GEMS.JK", "GGRM.JK",
    "GIAA.JK", "GJTL.JK", "GLOB.JK", "GMTD.JK", "GOLD.JK",
    "GOLL.JK", "GPRA.JK", "GSMF.JK", "GTBO.JK", "GWSA.JK",
    "GZCO.JK", "HADE.JK", "HDFA.JK", "HERO.JK", "HEXA.JK",
    "HITS.JK", "HMSP.JK", "HOME.JK", "HOTL.JK", "HRUM.JK",
    "IATA.JK", "IBFN.JK", "IBST.JK", "ICBP.JK", "ICON.JK",
    "IGAR.JK", "IIKP.JK", "IKAI.JK", "IKBI.JK", "IMAS.JK",
    "IMJS.JK", "IMPC.JK", "INAF.JK", "INAI.JK", "INCI.JK",
    "INCO.JK", "INDF.JK", "INDR.JK", "INDS.JK", "INDX.JK",
    "INDY.JK", "INKP.JK", "INPC.JK", "INPP.JK", "INRU.JK",
    "INTA.JK", "INTD.JK", "INTP.JK", "IPOL.JK", "ISAT.JK",
    "ISSP.JK", "ITMA.JK", "ITMG.JK", "JAWA.JK", "JECC.JK",
    "JIHD.JK", "JKON.JK", "JPFA.JK", "JRPT.JK", "JSMR.JK",
    "JSPT.JK", "JTPE.JK", "KAEF.JK", "KARW.JK", "KBLI.JK",
    "KBLM.JK", "KBLV.JK", "KBRI.JK", "KDSI.JK", "KIAS.JK",
    "KICI.JK", "KIJA.JK", "KKGI.JK", "KLBF.JK", "KOBX.JK",
    "KOIN.JK", "KONI.JK", "KOPI.JK", "KPIG.JK", "KRAS.JK",
    "KREN.JK", "LAPD.JK", "LCGP.JK", "LEAD.JK", "LINK.JK",
    "LION.JK", "LMAS.JK", "LMPI.JK", "LMSH.JK", "LPCK.JK",
    "LPGI.JK", "LPIN.JK", "LPKR.JK", "LPLI.JK", "LPPF.JK",
    "LPPS.JK", "LRNA.JK", "LSIP.JK", "LTLS.JK", "MAGP.JK",
    "MAIN.JK", "MAPI.JK", "MAYA.JK", "MBAP.JK", "MBSS.JK",
    "MBTO.JK", "MCOR.JK", "MDIA.JK", "MDKA.JK", "MDLN.JK",
    "MDRN.JK", "MEDC.JK", "MEGA.JK", "MERK.JK", "META.JK",
    "MFMI.JK", "MGNA.JK", "MICE.JK", "MIDI.JK", "MIKA.JK",
    "MIRA.JK", "MITI.JK", "MKPI.JK", "MLBI.JK", "MLIA.JK",
    "MLPL.JK", "MLPT.JK", "MMLP.JK", "MNCN.JK", "MPMX.JK",
    "MPPA.JK", "MRAT.JK", "MREI.JK", "MSKY.JK", "MTDL.JK",
    "MTFN.JK", "MTLA.JK", "MTSM.JK", "MYOH.JK", "MYOR.JK",
    "MYTX.JK", "NELY.JK", "NIKL.JK", "NIRO.JK", "NISP.JK",
    "NOBU.JK", "NRCA.JK", "OCAP.JK", "OKAS.JK", "OMRE.JK",
    "PADI.JK", "PALM.JK", "PANR.JK", "PANS.JK", "PBRX.JK",
    "PDES.JK", "PEGE.JK", "PGAS.JK", "PGLI.JK", "PICO.JK",
    "PJAA.JK", "PKPK.JK", "PLAS.JK", "PLIN.JK", "PNBN.JK",
    "PNBS.JK", "PNIN.JK", "PNLF.JK", "PSAB.JK", "PSDN.JK",
    "PSKT.JK", "PTBA.JK", "PTIS.JK", "PTPP.JK", "PTRO.JK",
    "PTSN.JK", "PTSP.JK", "PUDP.JK", "PWON.JK", "PYFA.JK",
    "RAJA.JK", "RALS.JK", "RANC.JK", "RBMS.JK", "RDTX.JK",
    "RELI.JK", "RICY.JK", "RIGS.JK", "RIMO.JK", "RODA.JK",
    "ROTI.JK", "RUIS.JK", "SAFE.JK", "SAME.JK", "SCCO.JK",
    "SCMA.JK", "SCPI.JK", "SDMU.JK", "SDPC.JK", "SDRA.JK",
    "SGRO.JK", "SHID.JK", "SIDO.JK", "SILO.JK", "SIMA.JK",
    "SIMP.JK", "SIPD.JK", "SKBM.JK", "SKLT.JK", "SKYB.JK",
    "SMAR.JK", "SMBR.JK", "SMCB.JK", "SMDM.JK", "SMDR.JK",
    "SMGR.JK", "SMMA.JK", "SMMT.JK", "SMRA.JK", "SMRU.JK",
    "SMSM.JK", "SOCI.JK", "SONA.JK", "SPMA.JK", "SQMI.JK",
    "SRAJ.JK", "SRIL.JK", "SRSN.JK", "SRTG.JK", "SSIA.JK",
    "SSMS.JK", "SSTM.JK", "STAR.JK", "STTP.JK", "SUGI.JK",
    "SULI.JK", "SUPR.JK", "TALF.JK", "TARA.JK", "TAXI.JK",
    "TBIG.JK", "TBLA.JK", "TBMS.JK", "TCID.JK", "TELE.JK",
    "TFCO.JK", "TGKA.JK", "TIFA.JK", "TINS.JK", "TIRA.JK",
    "TIRT.JK", "TKIM.JK", "TLKM.JK", "TMAS.JK", "TMPO.JK",
    "TOBA.JK", "TOTL.JK", "TOTO.JK", "TOWR.JK", "TPIA.JK",
    "TPMA.JK", "TRAM.JK", "TRIL.JK", "TRIM.JK", "TRIO.JK",
    "TRIS.JK", "TRST.JK", "TRUS.JK", "TSPC.JK", "ULTJ.JK",
    "UNIC.JK", "UNIT.JK", "UNSP.JK", "UNTR.JK", "UNVR.JK",
    "VICO.JK", "VINS.JK", "VIVA.JK", "VOKS.JK", "VRNA.JK",
    "WAPO.JK", "WEHA.JK", "WICO.JK", "WIIM.JK", "WIKA.JK",
    "WINS.JK", "WOMF.JK", "WSKT.JK", "WTON.JK", "YPAS.JK",
    "YULE.JK", "ZBRA.JK", "SHIP.JK", "CASA.JK", "DAYA.JK",
    "DPUM.JK", "IDPR.JK", "JGLE.JK", "KINO.JK", "MARI.JK",
    "MKNT.JK", "MTRA.JK", "OASA.JK", "POWR.JK", "INCF.JK",
    "WSBP.JK", "PBSA.JK", "PRDA.JK", "BOGA.JK", "BRIS.JK",
    "PORT.JK", "CARS.JK", "MINA.JK", "CLEO.JK", "TAMU.JK",
    "CSIS.JK", "TGRA.JK", "FIRE.JK", "TOPS.JK", "KMTR.JK",
    "ARMY.JK", "MAPB.JK", "WOOD.JK", "HRTA.JK", "MABA.JK",
    "HOKI.JK", "MPOW.JK", "MARK.JK", "NASA.JK", "MDKI.JK",
    "BELL.JK", "KIOS.JK", "GMFI.JK", "MTWI.JK", "ZINC.JK",
    "MCAS.JK", "PPRE.JK", "WEGE.JK", "PSSI.JK", "MORA.JK",
    "DWGL.JK", "PBID.JK", "JMAS.JK", "CAMP.JK", "IPCM.JK",
    "PCAR.JK", "LCKM.JK", "BOSS.JK", "HELI.JK", "JSKY.JK",
    "INPS.JK", "GHON.JK", "TDPM.JK", "DFAM.JK", "NICK.JK",
    "BTPS.JK", "SPTO.JK", "PRIM.JK", "HEAL.JK", "TRUK.JK",
    "PZZA.JK", "TUGU.JK", "MSIN.JK", "SWAT.JK", "TNCA.JK",
    "MAPA.JK", "TCPI.JK", "IPCC.JK", "RISE.JK", "BPTR.JK",
    "POLL.JK", "NFCX.JK", "MGRO.JK", "NUSA.JK", "FILM.JK",
    "ANDI.JK", "LAND.JK", "MOLI.JK", "PANI.JK", "DIGI.JK",
    "CITY.JK", "SAPX.JK", "SURE.JK", "HKMU.JK", "MPRO.JK",
    "DUCK.JK", "GOOD.JK", "SKRN.JK", "YELO.JK", "CAKK.JK",
    "SATU.JK", "SOSS.JK", "DEAL.JK", "POLA.JK", "DIVA.JK",
    "LUCK.JK", "URBN.JK", "SOTS.JK", "ZONE.JK", "PEHA.JK",
    "FOOD.JK", "BEEF.JK", "POLI.JK", "CLAY.JK", "NATO.JK",
    "JAYA.JK", "COCO.JK", "MTPS.JK", "CPRI.JK", "HRME.JK",
    "POSA.JK", "JAST.JK", "FITT.JK", "BOLA.JK", "CCSI.JK",
    "SFAN.JK", "POLU.JK", "KJEN.JK", "KAYU.JK", "ITIC.JK",
    "PAMG.JK", "IPTV.JK", "BLUE.JK", "ENVY.JK", "EAST.JK",
    "LIFE.JK", "FUJI.JK", "KOTA.JK", "INOV.JK", "ARKA.JK",
    "SMKL.JK", "HDIT.JK", "KEEN.JK", "BAPI.JK", "TFAS.JK",
    "GGRP.JK", "OPMS.JK", "NZIA.JK", "SLIS.JK", "PURE.JK",
    "IRRA.JK", "DMMX.JK", "SINI.JK", "WOWS.JK", "ESIP.JK",
    "TEBE.JK", "KEJU.JK", "PSGO.JK", "AGAR.JK", "IFSH.JK",
    "REAL.JK", "IFII.JK", "PMJS.JK", "UCID.JK", "GLVA.JK",
    "PGJO.JK", "AMAR.JK", "CSRA.JK", "INDO.JK", "AMOR.JK",
    "TRIN.JK", "DMND.JK", "PURA.JK", "PTPW.JK", "TAMA.JK",
    "IKAN.JK", "SAMF.JK", "SBAT.JK", "KBAG.JK", "CBMF.JK",
    "RONY.JK", "CSMI.JK", "BBSS.JK", "BHAT.JK", "CASH.JK",
    "TECH.JK", "EPAC.JK", "UANG.JK", "PGUN.JK", "SOFA.JK",
    "PPGL.JK", "TOYS.JK", "SGER.JK", "TRJA.JK", "PNGO.JK",
    "SCNP.JK", "BBSI.JK", "KMDS.JK", "PURI.JK", "SOHO.JK",
    "HOMI.JK", "ROCK.JK", "ENZO.JK", "PLAN.JK", "PTDU.JK",
    "ATAP.JK", "VICI.JK", "PMMP.JK", "BANK.JK", "WMUU.JK",
    "EDGE.JK", "UNIQ.JK", "BEBS.JK", "SNLK.JK", "ZYRX.JK",
    "LFLO.JK", "FIMP.JK", "TAPG.JK", "NPGF.JK", "LUCY.JK",
    "ADCP.JK", "HOPE.JK", "MGLV.JK", "TRUE.JK", "LABA.JK",
    "ARCI.JK", "IPAC.JK", "MASB.JK", "BMHS.JK", "FLMC.JK",
    "NICL.JK", "UVCR.JK", "BUKA.JK", "HAIS.JK", "OILS.JK",
    "GPSO.JK", "MCOL.JK", "RSGK.JK", "RUNS.JK", "SBMA.JK",
    "CMNT.JK", "GTSI.JK", "IDEA.JK", "KUAS.JK", "BOBA.JK",
    "MTEL.JK", "DEPO.JK", "BINO.JK", "CMRY.JK", "WGSH.JK",
    "TAYS.JK", "WMPP.JK", "RMKE.JK", "OBMD.JK", "AVIA.JK",
    "IPPE.JK", "NASI.JK", "BSML.JK", "DRMA.JK", "ADMR.JK",
    "SEMA.JK", "ASLC.JK", "NETV.JK", "BAUT.JK", "ENAK.JK",
    "NTBK.JK", "SMKM.JK", "STAA.JK", "NANO.JK", "BIKE.JK",
    "WIRG.JK", "SICO.JK", "GOTO.JK", "TLDN.JK", "MTMH.JK",
    "WINR.JK", "IBOS.JK", "OLIV.JK", "ASHA.JK", "SWID.JK",
    "TRGU.JK", "ARKO.JK", "CHEM.JK", "DEWI.JK", "AXIO.JK",
    "KRYA.JK", "HATM.JK", "RCCC.JK", "GULA.JK", "JARR.JK",
    "AMMS.JK", "RAFI.JK", "KKES.JK", "ELPI.JK", "EURO.JK",
    "KLIN.JK", "TOOL.JK", "BUAH.JK", "CRAB.JK", "MEDS.JK",
    "COAL.JK", "PRAY.JK", "CBUT.JK", "BELI.JK", "MKTR.JK",
    "OMED.JK", "BSBK.JK", "PDPP.JK", "KDTN.JK", "ZATA.JK",
    "NINE.JK", "MMIX.JK", "PADA.JK", "ISAP.JK", "VTNY.JK",
    "SOUL.JK", "ELIT.JK", "BEER.JK", "CBPE.JK", "SUNI.JK",
    "CBRE.JK", "WINE.JK", "BMBL.JK", "PEVE.JK", "LAJU.JK",
    "FWCT.JK", "NAYZ.JK", "IRSX.JK", "PACK.JK", "VAST.JK",
    "CHIP.JK", "HALO.JK", "KING.JK", "PGEO.JK", "FUTR.JK",
    "HILL.JK", "BDKR.JK", "PTMP.JK", "SAGE.JK", "TRON.JK",
    "CUAN.JK", "NSSS.JK", "GTRA.JK", "HAJJ.JK", "JATI.JK",
    "TYRE.JK", "MPXL.JK", "SMIL.JK", "KLAS.JK", "MAXI.JK",
    "VKTR.JK", "RELF.JK", "AMMN.JK", "CRSN.JK", "GRPM.JK",
    "WIDI.JK", "TGUK.JK", "INET.JK", "MAHA.JK", "RMKO.JK",
    "CNMA.JK", "FOLK.JK", "HBAT.JK", "GRIA.JK", "PPRI.JK",
    "ERAL.JK", "CYBR.JK", "MUTU.JK", "LMAX.JK", "HUMI.JK",
    "MSIE.JK", "RSCH.JK", "BABY.JK", "AEGS.JK", "IOTF.JK",
    "KOCI.JK", "PTPS.JK", "BREN.JK", "STRK.JK", "KOKA.JK",
    "LOPI.JK", "UDNG.JK", "RGAS.JK", "MSTI.JK", "IKPM.JK",
    "AYAM.JK", "SURI.JK", "ASLI.JK", "GRPH.JK", "SMGA.JK",
    "UNTD.JK", "TOSK.JK", "MPIX.JK", "ALII.JK", "MKAP.JK",
    "MEJA.JK", "LIVE.JK", "HYGN.JK", "BAIK.JK", "VISI.JK",
    "AREA.JK", "MHKI.JK", "ATLA.JK", "DATA.JK", "SOLA.JK",
    "BATR.JK", "SPRE.JK", "PART.JK", "GOLF.JK", "ISEA.JK",
    "BLES.JK", "GUNA.JK", "LABS.JK", "DOSS.JK", "NEST.JK",
    "PTMR.JK", "VERN.JK", "DAAZ.JK", "BOAT.JK", "NAIK.JK",
    "AADI.JK", "MDIY.JK", "KSIX.JK", "RATU.JK", "YOII.JK",
    "HGII.JK", "BRRC.JK", "DGWG.JK", "CBDK.JK", "OBAT.JK",
    "MINE.JK", "ASPR.JK", "PSAT.JK", "COIN.JK", "CDIA.JK",
    "BLOG.JK", "MERI.JK", "CHEK.JK", "PMUI.JK", "EMAS.JK",
    "PJHB.JK", "RLCO.JK", "SUPA.JK", "KAQI.JK", "YUPI.JK",
    "FORE.JK", "MDLA.JK", "DKHH.JK", "AYLS.JK", "DADA.JK",
    "ASPI.JK", "ESTA.JK", "BESS.JK", "AMAN.JK", "CARE.JK",
    "PIPA.JK", "NCKL.JK", "MENN.JK", "AWAN.JK", "MBMA.JK",
    "RAAM.JK", "DOOH.JK", "CGAS.JK", "NICE.JK", "MSJA.JK",
    "SMLE.JK", "ACRO.JK", "MANG.JK", "WIFI.JK", "FAPA.JK",
    "DCII.JK", "KETR.JK", "DGNS.JK", "UFOE.JK", "ADMF.JK",
    "ADMG.JK", "ADRO.JK", "AGII.JK", "AGRO.JK", "AGRS.JK",
    "AHAP.JK", "AIMS.JK", "PNSE.JK", "POLY.JK", "POOL.JK",
    "PPRO.JK",
]


# ─────────────────────────────────────────────
# RS SCORE CALCULATION
# ─────────────────────────────────────────────

def get_date_range():
    end   = datetime.date.today()
    start = end - datetime.timedelta(days=HISTORY_DAYS)
    return start, end


def validate_price_series(series, ticker=""):
    """
    Runs 4 data quality checks on a raw price series.
    Returns (cleaned Series, None) on success, or (None, reason) on failure.
    """
    # Check 1: minimum price
    if series.iloc[-1] < MIN_PRICE:
        return None, "price_below_min"

    # Check 2: stale price ratio
    stale_ratio = (series.diff().eq(0)).mean()
    if stale_ratio > MAX_STALE_RATIO:
        return None, "stale_ratio"

    # Check 3: outlier removal via rolling median
    rolling_med = series.rolling(window=20, min_periods=5, center=True).median()
    ratio       = series / rolling_med
    mask        = (ratio >= 1 / OUTLIER_FACTOR) & (ratio <= OUTLIER_FACTOR)

    # Check 4: still enough non-outlier bars after cleaning
    if mask.sum() < MIN_TRADING_DAYS:
        return None, "too_few_non_outlier_bars"

    # Replace outliers with nearest valid price to preserve positional alignment
    return series.where(mask).ffill().bfill(), None


def fetch_price_history(ticker, start, end):
    """
    Fetches adjusted close prices and runs data quality validation.
    Returns (cleaned_close_series, avg_30d_volume, reason).
    On success: (series, vol_or_None, None).
    On failure: (None, None, reason_string).

    Uses yf.Ticker().history() instead of yf.download() because the latter
    shares internal state that causes data cross-contamination under
    concurrent ThreadPoolExecutor calls.
    """
    try:
        t = yf.Ticker(ticker)
        df = t.history(start=start, end=end, auto_adjust=True)
        if df.empty or "Close" not in df.columns:
            return None, None, "download_empty_or_no_close"
        series = df["Close"].squeeze().dropna()
        if len(series) < MIN_TRADING_DAYS:
            return None, None, "too_few_raw_bars"

        avg_vol = None
        if "Volume" in df.columns:
            vol = df["Volume"].squeeze().dropna()
            if len(vol) >= 30:
                avg_vol = int(vol.iloc[-30:].mean())

        cleaned, vreason = validate_price_series(series, ticker)
        if cleaned is None:
            return None, None, vreason
        return cleaned, avg_vol, None
    except Exception:
        return None, None, "fetch_exception"


class RateLimiter:
    """Thread-safe minimum interval guard for outbound API calls."""
    def __init__(self, min_interval):
        self.min_interval = float(min_interval)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self):
        if self.min_interval <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next_allowed:
                    self._next_allowed = now + self.min_interval
                    return
                sleep_for = self._next_allowed - now
            time.sleep(sleep_for)


def fetch_stock_info(ticker):
    """Fetches sector and industry from yfinance Ticker info."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("sector", ""), info.get("industry", "")
    except Exception:
        return "", ""


def align_series(stock_close, idx_close):
    """Inner-joins stock and index closes on date, drops NaNs."""
    combined = pd.concat([stock_close, idx_close], axis=1, join="inner").dropna()
    combined.columns = ["stock", "idx"]
    return combined


def calc_rs_score(combined):
    """
    Mirrors the Pine Script formula exactly:
        RS Score = weighted_perf_stock / weighted_perf_idx * 100
        Weights: Q1 (most recent) = 40%, Q2 = 20%, Q3 = 20%, Q4 = 20%
    Expects a pre-aligned DataFrame from align_series().
    Returns (score, None) on success, or (None, reason) on failure.
    """
    if len(combined) < 253:
        return None, "insufficient_overlap"

    def perf(col, lb):
        past = combined[col].iloc[-(lb + 1)]
        return combined[col].iloc[-1] / past if past != 0 else np.nan

    rs_stock = (0.4 * perf("stock", 63)  + 0.2 * perf("stock", 126)
              + 0.2 * perf("stock", 189) + 0.2 * perf("stock", 252))
    rs_idx   = (0.4 * perf("idx",   63)  + 0.2 * perf("idx",   126)
              + 0.2 * perf("idx",   189) + 0.2 * perf("idx",   252))

    if rs_idx == 0 or np.isnan(rs_stock) or np.isnan(rs_idx):
        return None, "invalid_perf"
    score = (rs_stock / rs_idx) * 100

    return score, None


def calc_single_tf_score(combined, lookback):
    """
    Calculates RS Score for a single timeframe (lookback in trading days).
    Used for the 1M / 3M / 6M / 12M percentile columns in the rankings.
    Expects a pre-aligned DataFrame from align_series().
    Returns float or None.
    """
    if len(combined) < lookback + 1:
        return None
    past_stock = combined["stock"].iloc[-(lookback + 1)]
    past_idx   = combined["idx"].iloc[-(lookback + 1)]
    if past_stock == 0 or past_idx == 0:
        return None
    perf_stock = combined["stock"].iloc[-1] / past_stock
    perf_idx   = combined["idx"].iloc[-1]   / past_idx
    if perf_idx == 0 or np.isnan(perf_stock) or np.isnan(perf_idx):
        return None
    return (perf_stock / perf_idx) * 100


def assign_percentile(score, arr):
    """
    Returns the percentile rank (0–99) of score within arr.
    Uses scipy-style: percentile = % of values strictly below this score.
    Expects a pre-built numpy array (None/NaN already filtered out).
    """
    if score is None or np.isnan(score):
        return None
    if len(arr) == 0:
        return None
    return int(round(np.mean(arr < score) * 100))


def assign_elite_flags(stock_data):
    """
    Tags each stock with elite_1m … elite_rs flags (top1/top2/None)
    and an elite_count tally.  Operates in-place on the stock_data list
    after percentiles have been assigned.

    Thresholds are derived from the already-discretized integer percentiles
    (0–99), so ties at a boundary value can inflate a tier beyond its nominal
    percentage (e.g. if 15 stocks share pct_1m=98, all 15 get top1).
    """
    dimensions = [
        ("elite_1m",  "pct_1m"),
        ("elite_3m",  "pct_3m"),
        ("elite_6m",  "pct_6m"),
        ("elite_12m", "pct_12m"),
        ("elite_rs",  "percentile"),
    ]
    for flag_col, data_col in dimensions:
        valid_scores = [d[data_col] for d in stock_data if d.get(data_col) is not None]
        if len(valid_scores) < 50:
            for d in stock_data:
                d[flag_col] = None
            continue
        top1_threshold = np.percentile(valid_scores, 99)
        top2_threshold = np.percentile(valid_scores, 98)
        for d in stock_data:
            v = d.get(data_col)
            if v is None:
                d[flag_col] = None
            elif v >= top1_threshold:
                d[flag_col] = "top1"
            elif v >= top2_threshold:
                d[flag_col] = "top2"
            else:
                d[flag_col] = None

    elite_keys = ["elite_1m", "elite_3m", "elite_6m", "elite_12m", "elite_rs"]
    for d in stock_data:
        d["elite_count"] = sum(1 for k in elite_keys if d.get(k) is not None)


def calc_thresholds(scores):
    """
    Derives the 7 percentile threshold values from the RS score distribution.
    These map directly to the 7 manual input fields in the TradingView indicator.
    """
    arr = np.array(scores)
    return {
        "p99_for_99_stocks":  float(np.percentile(arr, 99)),
        "p90_for_90+_stocks": float(np.percentile(arr, 90)),
        "p70_for_70+_stocks": float(np.percentile(arr, 70)),
        "p50_for_50+_stocks": float(np.percentile(arr, 50)),
        "p30_for_30+_stocks": float(np.percentile(arr, 30)),
        "p10_for_10+_stocks": float(np.percentile(arr, 10)),
        "p1_for_1-_stocks":   float(np.percentile(arr,  1)),
    }


# ─────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────

def print_results(thresholds, date_str, score_count):
    print("\n" + "="*55)
    print(f"  IDX RS THRESHOLD RESULTS — {date_str}")
    print(f"  Stocks calculated: {score_count}")
    print("="*55)
    print("\n  📋 PASTE THESE INTO TRADINGVIEW INDICATOR INPUTS:\n")
    labels = [
        ("For 99 stocks  (p99)", "p99_for_99_stocks"),
        ("For 90+ stocks (p90)", "p90_for_90+_stocks"),
        ("For 70+ stocks (p70)", "p70_for_70+_stocks"),
        ("For 50+ stocks (p50)", "p50_for_50+_stocks"),
        ("For 30+ stocks (p30)", "p30_for_30+_stocks"),
        ("For 10+ stocks (p10)", "p10_for_10+_stocks"),
        ("For 1-  stocks (p1) ", "p1_for_1-_stocks"),
    ]
    for label, key in labels:
        print(f"  {label}: {thresholds[key]:.2f}")
    print("\n" + "="*55)


def prune_old_files(directory, pattern, keep=30):
    """
    Deletes oldest files in directory matching pattern, retaining only the
    most recent `keep` files. Safe to call even if fewer than `keep` exist.
    """
    files = sorted(glob.glob(os.path.join(directory, pattern)))
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        try:
            os.remove(f)
        except OSError:
            pass
    if to_delete:
        print(f"   🗑  Pruned {len(to_delete)} old file(s) from {directory}")


def ensure_output_dirs():
    os.makedirs(THRESHOLDS_DIR,  exist_ok=True)
    os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)
    os.makedirs(RANKINGS_DIR,    exist_ok=True)
    prune_old_files(RANKINGS_DIR,    "idx_rs_rankings_*.csv",    keep=FILE_RETENTION_KEEP)
    prune_old_files(THRESHOLDS_DIR,  "idx_rs_thresholds_*.csv",  keep=FILE_RETENTION_KEEP)
    prune_old_files(DIAGNOSTICS_DIR, "idx_rs_diagnostics_*.csv", keep=FILE_RETENTION_KEEP)


def build_output_paths(date_str):
    stamp = f"{date_str}_{datetime.datetime.now().strftime('%H%M%S')}"
    return {
        "thresholds":  os.path.join(THRESHOLDS_DIR,  f"idx_rs_thresholds_{stamp}.csv"),
        "diagnostics": os.path.join(DIAGNOSTICS_DIR, f"idx_rs_diagnostics_{stamp}.csv"),
        "rankings":    os.path.join(RANKINGS_DIR,    f"idx_rs_rankings_{stamp}.csv"),
    }


def save_to_csv(thresholds, date_str, score_count, output_path):
    row    = {"date": date_str, "stock_count": score_count, **thresholds}
    df_new = pd.DataFrame([row])
    df_new.to_csv(output_path, index=False)
    print(f"\n✅ Threshold CSV saved to: {output_path}")


REJECT_REASON_KEYS = (
    "download_empty_or_no_close",
    "too_few_raw_bars",
    "price_below_min",
    "stale_ratio",
    "too_few_non_outlier_bars",
    "fetch_exception",
)
SKIP_REASON_KEYS = ("insufficient_overlap", "invalid_perf", "below_rs_min")


def save_diagnostics_csv(row, output_path):
    df_new = pd.DataFrame([row])
    df_new.to_csv(output_path, index=False)
    print(f"\n✅ Diagnostics CSV saved to: {output_path}")


def print_diagnostics_summary(reject_counter, skip_counter, scored, universe_total, coverage_pct):
    print("\n📊 Coverage diagnostics")
    print(f"   Scored    : {scored} / {universe_total} ({coverage_pct:.1f}% coverage)")
    if reject_counter:
        print("   Top reject reasons:")
        for reason, cnt in reject_counter.most_common(5):
            print(f"      {reason}: {cnt}")
    if skip_counter:
        print("   Skip reasons (passed download, failed RS score):")
        for reason, cnt in skip_counter.most_common():
            print(f"      {reason}: {cnt}")
    if coverage_pct < WARN_COVERAGE_PCT or scored < WARN_MIN_SCORED:
        print(
            f"   ⚠ Warning: coverage < {WARN_COVERAGE_PCT}% or scored < {WARN_MIN_SCORED} "
            "— percentile context is weaker; interpret rankings cautiously."
        )


def build_diagnostics_row(date_str, universe_total, scored, rejected, skipped,
                          reject_counter, skip_counter):
    coverage_pct = 100.0 * scored / universe_total if universe_total else 0.0
    row = {
        "date":            date_str,
        "universe_total":  universe_total,
        "scored":          scored,
        "rejected":        rejected,
        "skipped":         skipped,
        "coverage_pct":    round(coverage_pct, 2),
    }
    for k in REJECT_REASON_KEYS:
        row[f"reject_{k}"] = reject_counter.get(k, 0)
    row["reject_misc"] = sum(
        c for k, c in reject_counter.items() if k not in REJECT_REASON_KEYS
    )
    for k in SKIP_REASON_KEYS:
        row[f"skip_{k}"] = skip_counter.get(k, 0)
    row["skip_misc"] = sum(
        c for k, c in skip_counter.items() if k not in SKIP_REASON_KEYS
    )
    return row


# ─────────────────────────────────────────────
# RANKINGS OUTPUT
# ─────────────────────────────────────────────

def save_rankings(ranked, date_str, output_path):
    """Saves the full ranked list to a dated CSV file."""
    rows = []
    for d in ranked:
        rows.append({
            "rank":              d["rank"],
            "ticker":            d["ticker"],
            "sector":            d.get("sector"),
            "industry":          d.get("industry"),
            "avg_vol_30d":       d.get("avg_vol_30d"),
            "price":             d.get("price"),
            "rs_score":          d["rs_score"],
            "rs_delta":          d.get("rs_delta"),
            "rs_delta_momentum": d.get("rs_delta_momentum"),
            "pct_from_52w_high": d.get("pct_from_52w_high"),
            "pct_from_52w_low":  d.get("pct_from_52w_low"),
            "range_position":    d.get("range_position"),
            "price_vs_sma10":    d.get("price_vs_sma10"),
            "price_vs_sma20":    d.get("price_vs_sma20"),
            "price_vs_sma50":    d.get("price_vs_sma50"),
            "price_vs_sma200":   d.get("price_vs_sma200"),
            "percentile":        d.get("percentile"),
            "pct_1m":            d.get("pct_1m"),
            "pct_3m":            d.get("pct_3m"),
            "pct_6m":            d.get("pct_6m"),
            "pct_12m":           d.get("pct_12m"),
            "elite_rs":          d.get("elite_rs"),
            "elite_1m":          d.get("elite_1m"),
            "elite_3m":          d.get("elite_3m"),
            "elite_6m":          d.get("elite_6m"),
            "elite_12m":         d.get("elite_12m"),
            "elite_count":       d.get("elite_count", 0),
            "date":              date_str,
        })
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"\n📊 Full rankings saved to: {output_path}")


def print_top_n(ranked, n):
    """Prints top N stocks as a clean table to the terminal."""
    top = ranked[:n]
    width = 131
    print(f"\n{'─'*width}")
    print(f"  TOP {n} IDX STOCKS BY RS SCORE")
    print(f"{'─'*width}")
    header = (
        f"  {'Rank':<5} {'Ticker':<8} {'Price':<8} {'SMA10':<7} {'SMA20':<7} "
        f"{'RS':<8} {'RSΔ':<7} {'52W%':<7} {'Rng':<6} "
        f"{'SMA50':<7} {'SMA200':<7} "
        f"{'Pct':<5} {'1M%':<5} {'3M%':<5} {'6M%':<5} {'12M%':<5} {'Elit':<4}"
    )
    print(header)
    print(f"  {'─'*width}")

    def _fmt(val, fmt_str=".1f"):
        if val is None:
            return "-"
        if isinstance(val, float) and np.isnan(val):
            return "-"
        return f"{val:{fmt_str}}"

    for d in top:
        prc   = _fmt(d.get('price'), '.0f')
        sm1   = _fmt(d.get('price_vs_sma10'))
        sm2   = _fmt(d.get('price_vs_sma20'))
        rs    = _fmt(d['rs_score'], '.2f')
        rsd   = _fmt(d.get('rs_delta'), '.2f')
        p52   = _fmt(d.get('pct_from_52w_high'))
        rng   = _fmt(d.get('range_position'))
        sma5  = _fmt(d.get('price_vs_sma50'))
        sma2  = _fmt(d.get('price_vs_sma200'))
        pct   = str(d['percentile']) if d['percentile'] is not None else '-'
        p1m   = str(d['pct_1m'])     if d['pct_1m']     is not None else '-'
        p3m   = str(d['pct_3m'])     if d['pct_3m']     is not None else '-'
        p6m   = str(d['pct_6m'])     if d['pct_6m']     is not None else '-'
        p12m  = str(d['pct_12m'])    if d['pct_12m']    is not None else '-'
        ec    = str(d.get('elite_count', 0))
        print(
            f"  {d['rank']:<5} {d['ticker']:<8} {prc:<8} {sm1:<7} {sm2:<7} "
            f"{rs:<8} {rsd:<7} {p52:<7} {rng:<6} "
            f"{sma5:<7} {sma2:<7} "
            f"{pct:<5} {p1m:<5} {p3m:<5} {p6m:<5} {p12m:<5} {ec:<4}"
        )
    print(f"{'─'*width}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    start, end = get_date_range()
    date_str   = end.strftime("%Y-%m-%d")
    ensure_output_dirs()
    output_paths = build_output_paths(date_str)

    print(f"\n🔄 IDX RS Threshold Calculator")
    print(f"   Date    : {date_str}")
    print(f"   History : {start} → {end}")
    print(f"   Min bars: {MIN_TRADING_DAYS} trading days")
    print(f"   Workers : {MAX_WORKERS}")
    print(f"   Universe: {len(IDX_TICKERS)} stocks\n")

    # Step 1: Fetch IDX Composite
    print("📥 Fetching IDX Composite (^JKSE)...")
    idx_close, _, _ = fetch_price_history(IDX_TICKER, start, end)
    if idx_close is None:
        print("❌ Failed to fetch IDX Composite. Check your internet connection.")
        return
    print(f"   ✓ {len(idx_close)} bars\n")

    # Step 2: Pre-cache stock metadata in parallel
    print("📥 Pre-caching stock sector/industry metadata...")
    info_cache = {}
    info_limiter = RateLimiter(REQUEST_DELAY)

    def _fetch_info_worker(ticker):
        info_limiter.wait()
        return ticker, fetch_stock_info(ticker)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_fetch_info_worker, ticker) for ticker in IDX_TICKERS]
        for fut in tqdm(as_completed(futures), total=len(futures), ncols=70):
            ticker, info = fut.result()
            info_cache[ticker] = info

    # Step 3: Fetch each stock and calculate RS Scores (12M composite + 4 timeframes)
    print("\n📥 Fetching stock prices and calculating RS Scores...")

    # stock_data: list of dicts, one per successfully scored stock
    stock_data = []
    all_valid_rs_scores = []
    failed, skipped = [], []
    reject_counter = Counter()
    skip_counter   = Counter()

    price_limiter = RateLimiter(REQUEST_DELAY)

    def _process_ticker(ticker):
        price_limiter.wait()
        close, avg_vol, fetch_reason = fetch_price_history(ticker, start, end)
        if close is None:
            return {
                "kind": "rejected",
                "ticker": ticker,
                "reason": fetch_reason or "unknown",
            }

        last_close = float(close.iloc[-1])
        price = round(last_close, 0)

        pct_from_52w_high = None
        pct_from_52w_low  = None
        range_position    = None
        if len(close) >= 252:
            recent_252 = close.iloc[-252:]
            high_52w = recent_252.max()
            low_52w  = recent_252.min()
            if high_52w and not np.isnan(high_52w) and high_52w != 0:
                pct_from_52w_high = round((last_close - high_52w) / high_52w * 100, 1)
            if low_52w and not np.isnan(low_52w) and low_52w != 0:
                pct_from_52w_low = round((last_close - low_52w) / low_52w * 100, 1)
            if (high_52w - low_52w) > 0:
                range_position = round((last_close - low_52w) / (high_52w - low_52w) * 100, 1)

        sma10  = float(close.rolling(10).mean().iloc[-1])  if len(close) >= 10  else None
        sma20  = float(close.rolling(20).mean().iloc[-1])  if len(close) >= 20  else None
        sma50  = float(close.rolling(50).mean().iloc[-1])  if len(close) >= 50  else None
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        def _valid_sma(v):
            return v is not None and not np.isnan(v) and v != 0

        price_vs_sma10  = round((last_close - sma10)  / sma10  * 100, 1) if _valid_sma(sma10)  else None
        price_vs_sma20  = round((last_close - sma20)  / sma20  * 100, 1) if _valid_sma(sma20)  else None
        price_vs_sma50  = round((last_close - sma50)  / sma50  * 100, 1) if _valid_sma(sma50)  else None
        price_vs_sma200 = round((last_close - sma200) / sma200 * 100, 1) if _valid_sma(sma200) else None

        combined = align_series(close, idx_close)

        # 12M composite score before RS_SCORE_MIN filtering.
        score_12m, rs_reason = calc_rs_score(combined)
        if score_12m is None:
            return {
                "kind": "skipped",
                "ticker": ticker,
                "reason": rs_reason or "unknown",
            }

        rs_delta = None
        # 4-week delta uses ~21 trading bars lookback. Needs extra overlap:
        # calc_rs_score() requires >=253 bars, so combined must be >=274 bars to compute 4w-ago.
        if len(combined) >= 274:
            combined_4w_ago = combined.iloc[:-21]
            score_4w_ago, _ = calc_rs_score(combined_4w_ago)
            if score_4w_ago is not None and not np.isnan(score_4w_ago):
                rs_delta = round(score_12m - score_4w_ago, 2)

        rs_delta_momentum = None
        # Requires 253 + 21 + 21 + 21 = 316 aligned bars minimum
        if len(combined) >= 316:
            combined_4w_ago = combined.iloc[:-21]
            combined_8w_ago = combined.iloc[:-42]
            score_4w_ago, _ = calc_rs_score(combined_4w_ago)
            score_8w_ago, _ = calc_rs_score(combined_8w_ago)
            if (score_4w_ago is not None and score_8w_ago is not None
                    and not np.isnan(score_4w_ago) and not np.isnan(score_8w_ago)):
                delta_now     = score_12m   - score_4w_ago
                delta_4w_ago  = score_4w_ago - score_8w_ago
                rs_delta_momentum = round(delta_now - delta_4w_ago, 2)

        # Single-timeframe scores (1M=21d, 3M=63d, 6M=126d, 12M=252d)
        s1m  = calc_single_tf_score(combined, 21)
        s3m  = calc_single_tf_score(combined, 63)
        s6m  = calc_single_tf_score(combined, 126)
        s12m = calc_single_tf_score(combined, 252)

        sector, industry = info_cache.get(ticker, ("", ""))

        if score_12m < RS_SCORE_MIN:
            return {
                "kind": "below_min",
                "ticker": ticker,
                "reason": "below_rs_min",
                "raw_rs_score": score_12m,
            }

        return {
            "kind": "scored",
            "ticker": ticker,
            "raw_rs_score": score_12m,
            "record": {
                "ticker":       ticker.replace(".JK", ""),
                "sector":       sector,
                "industry":     industry,
                "avg_vol_30d":  avg_vol,
                "price":        price,
                "rs_score":     round(score_12m, 2),
                "rs_delta":     rs_delta,
                "rs_delta_momentum": rs_delta_momentum,
                "pct_from_52w_high": pct_from_52w_high,
                "pct_from_52w_low":  pct_from_52w_low,
                "range_position":    range_position,
                "price_vs_sma10":    price_vs_sma10,
                "price_vs_sma20":    price_vs_sma20,
                "price_vs_sma50":    price_vs_sma50,
                "price_vs_sma200":   price_vs_sma200,
                "s1m":          s1m,
                "s3m":          s3m,
                "s6m":          s6m,
                "s12m":         s12m,
            },
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_process_ticker, ticker) for ticker in IDX_TICKERS]
        for fut in tqdm(as_completed(futures), total=len(futures), ncols=70):
            result = fut.result()
            kind = result["kind"]
            if kind == "rejected":
                reason = result["reason"]
                reject_counter[reason] += 1
                failed.append(result["ticker"])
                continue
            if kind == "skipped":
                reason = result["reason"]
                skip_counter[reason] += 1
                skipped.append(result["ticker"])
                continue
            if kind == "below_min":
                all_valid_rs_scores.append(result["raw_rs_score"])
                skip_counter["below_rs_min"] += 1
                skipped.append(result["ticker"])
                continue
            all_valid_rs_scores.append(result["raw_rs_score"])
            stock_data.append(result["record"])

    threshold_scores = [round(s, 2) for s in all_valid_rs_scores]
    ranked_scores = [d["rs_score"] for d in stock_data]

    universe_total = len(IDX_TICKERS)
    coverage_pct   = 100.0 * len(threshold_scores) / universe_total if universe_total else 0.0

    print(f"\n   ✓ Valid RS universe (for thresholds): {len(threshold_scores)} stocks")
    print(f"   ✓ Ranked stocks (RS >= {RS_SCORE_MIN}): {len(ranked_scores)} stocks")
    if failed:
        sample = ", ".join(failed[:5]) + ("..." if len(failed) > 5 else "")
        print(f"   ⚠ Rejected : {len(failed)} — no data / failed quality checks ({sample})")
    if skipped:
        print(f"   ⚠ Skipped  : {len(skipped)} (insufficient overlap / invalid perf / below RS min)")

    print_diagnostics_summary(reject_counter, skip_counter, len(threshold_scores), universe_total, coverage_pct)
    diag_row = build_diagnostics_row(
        date_str, universe_total, len(threshold_scores), len(failed), len(skipped),
        reject_counter, skip_counter,
    )
    save_diagnostics_csv(diag_row, output_paths["diagnostics"])

    if len(threshold_scores) < 30:
        print("\n❌ Too few stocks scored — results unreliable.")
        return

    # Step 3: Assign percentiles (pre-build arrays once, not per-stock)
    def _clean_scores(raw):
        return np.array([s for s in raw if s is not None and not np.isnan(s)])

    arr_12m  = _clean_scores(threshold_scores)
    arr_s1m  = _clean_scores([d["s1m"]  for d in stock_data])
    arr_s3m  = _clean_scores([d["s3m"]  for d in stock_data])
    arr_s6m  = _clean_scores([d["s6m"]  for d in stock_data])
    arr_s12m = _clean_scores([d["s12m"] for d in stock_data])

    for d in stock_data:
        d["percentile"]     = assign_percentile(d["rs_score"], arr_12m)
        d["pct_1m"]         = assign_percentile(d["s1m"],      arr_s1m)
        d["pct_3m"]         = assign_percentile(d["s3m"],      arr_s3m)
        d["pct_6m"]         = assign_percentile(d["s6m"],      arr_s6m)
        d["pct_12m"]        = assign_percentile(d["s12m"],     arr_s12m)

    assign_elite_flags(stock_data)

    # Step 4: Rank by 12M composite percentile (desc), then RS Score (desc)
    ranked = sorted(stock_data, key=lambda d: (d["percentile"] or 0, d["rs_score"]), reverse=True)
    for i, d in enumerate(ranked, 1):
        d["rank"] = i

    # Step 5: Threshold calibration (for TradingView manual inputs, full RS universe)
    thresholds = calc_thresholds(threshold_scores)
    print_results(thresholds, date_str, len(threshold_scores))
    save_to_csv(thresholds, date_str, len(threshold_scores), output_paths["thresholds"])

    # Step 6: Save full ranked list
    save_rankings(ranked, date_str, output_paths["rankings"])

    # Step 7: Print top N to terminal
    print_top_n(ranked, TOP_N_TERMINAL)

    print("\n  💡 Next step:")
    print("     Open TradingView → indicator settings → IDX RS Rating")
    print("     Paste the 7 values above into the matching input fields\n")


if __name__ == "__main__":
    main()