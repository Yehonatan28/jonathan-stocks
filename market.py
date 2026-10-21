"""Market-wide data: index constituents, batch quotes and CNN Fear & Greed.

Three things the per-ticker technical engine does not provide:

  * a constituent table with sector, market cap and company domain, which is
    what a sector treemap needs;
  * batch quotes, because 500 names cannot each have their own HTTP request;
  * CNN's published Fear & Greed index, read from the same JSON its own page
    reads rather than a number invented locally.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
}

_CACHE = {}


def _cached(key, ttl, build):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    value = build()
    _CACHE[key] = (time.time() + ttl, value)
    return value


# ------------------------------------------------- 1. index constituents ---
# ticker | company | sector | market cap ($B, a fallback for sizing) | domain
#
# The cap here is only a fallback: batch_quotes() returns the live market cap
# and that is preferred, because a hardcoded figure goes stale within weeks.
# The domain drives the logo lookup and is blank where it is not known, which
# the UI handles by falling back to the ticker text.

SECTOR_NAMES = {
    'TECH': 'Technology', 'FIN': 'Financials', 'HLTH': 'Health Care',
    'DISC': 'Consumer Discretionary', 'COMM': 'Communication Services',
    'INDU': 'Industrials', 'STPL': 'Consumer Staples', 'ENRG': 'Energy',
    'UTIL': 'Utilities', 'MATL': 'Materials', 'REAL': 'Real Estate',
}

SECTOR_ORDER = ['Technology', 'Financials', 'Health Care',
                'Consumer Discretionary', 'Communication Services',
                'Industrials', 'Consumer Staples', 'Energy', 'Utilities',
                'Materials', 'Real Estate']

_SP500_RAW = """\
NVDA|NVIDIA|TECH|4400|nvidia.com
MSFT|Microsoft|TECH|3800|microsoft.com
AAPL|Apple|TECH|3300|apple.com
AVGO|Broadcom|TECH|1300|broadcom.com
ORCL|Oracle|TECH|650|oracle.com
PLTR|Palantir|TECH|380|palantir.com
AMD|Advanced Micro Devices|TECH|290|amd.com
CSCO|Cisco|TECH|270|cisco.com
CRM|Salesforce|TECH|260|salesforce.com
IBM|IBM|TECH|250|ibm.com
INTU|Intuit|TECH|210|intuit.com
NOW|ServiceNow|TECH|190|servicenow.com
QCOM|Qualcomm|TECH|160|qualcomm.com
TXN|Texas Instruments|TECH|150|ti.com
ADBE|Adobe|TECH|140|adobe.com
AMAT|Applied Materials|TECH|130|appliedmaterials.com
MU|Micron Technology|TECH|110|micron.com
APH|Amphenol|TECH|110|amphenol.com
LRCX|Lam Research|TECH|110|lamresearch.com
APP|AppLovin|TECH|110|applovin.com
ANET|Arista Networks|TECH|100|arista.com
KLAC|KLA Corporation|TECH|100|kla.com
PANW|Palo Alto Networks|TECH|100|paloaltonetworks.com
CRWD|CrowdStrike|TECH|95|crowdstrike.com
INTC|Intel|TECH|95|intel.com
ADI|Analog Devices|TECH|90|analog.com
MRVL|Marvell Technology|TECH|70|marvell.com
SNPS|Synopsys|TECH|70|synopsys.com
CDNS|Cadence Design|TECH|75|cadence.com
ROP|Roper Technologies|TECH|55|ropertech.com
NXPI|NXP Semiconductors|TECH|55|nxp.com
FTNT|Fortinet|TECH|70|fortinet.com
ADSK|Autodesk|TECH|60|autodesk.com
WDAY|Workday|TECH|60|workday.com
TEL|TE Connectivity|TECH|45|te.com
MCHP|Microchip Technology|TECH|35|microchip.com
MSI|Motorola Solutions|TECH|70|motorolasolutions.com
IT|Gartner|TECH|30|gartner.com
GLW|Corning|TECH|45|corning.com
HPQ|HP Inc|TECH|28|hp.com
DELL|Dell Technologies|TECH|85|dell.com
HPE|Hewlett Packard Enterprise|TECH|28|hpe.com
STX|Seagate Technology|TECH|30|seagate.com
WDC|Western Digital|TECH|30|westerndigital.com
NTAP|NetApp|TECH|23|netapp.com
KEYS|Keysight Technologies|TECH|28|keysight.com
TDY|Teledyne|TECH|23|teledyne.com
ZBRA|Zebra Technologies|TECH|17|zebra.com
TER|Teradyne|TECH|22|teradyne.com
SWKS|Skyworks Solutions|TECH|11|skyworksinc.com
QRVO|Qorvo|TECH|8|qorvo.com
MPWR|Monolithic Power|TECH|35|monolithicpower.com
ON|ON Semiconductor|TECH|25|onsemi.com
FSLR|First Solar|TECH|22|firstsolar.com
ENPH|Enphase Energy|TECH|6|enphase.com
JBL|Jabil|TECH|18|jabil.com
SMCI|Super Micro Computer|TECH|25|supermicro.com
CTSH|Cognizant|TECH|35|cognizant.com
ACN|Accenture|TECH|200|accenture.com
INFY|Infosys|TECH|75|infosys.com
EPAM|EPAM Systems|TECH|11|epam.com
AKAM|Akamai|TECH|12|akamai.com
VRSN|VeriSign|TECH|25|verisign.com
GDDY|GoDaddy|TECH|25|godaddy.com
PTC|PTC Inc|TECH|21|ptc.com
ANSS|Ansys|TECH|30|ansys.com
TYL|Tyler Technologies|TECH|23|tylertech.com
CDW|CDW Corporation|TECH|25|cdw.com
FFIV|F5 Inc|TECH|15|f5.com
JNPR|Juniper Networks|TECH|12|juniper.net
TRMB|Trimble|TECH|17|trimble.com
GEN|Gen Digital|TECH|18|gendigital.com
FICO|Fair Isaac|TECH|45|fico.com
PAYC|Paycom|TECH|12|paycom.com
MANH|Manhattan Associates|TECH|14|manh.com
BRK-B|Berkshire Hathaway|FIN|1050|berkshirehathaway.com
JPM|JPMorgan Chase|FIN|800|jpmorganchase.com
V|Visa|FIN|640|visa.com
MA|Mastercard|FIN|530|mastercard.com
BAC|Bank of America|FIN|360|bankofamerica.com
WFC|Wells Fargo|FIN|260|wellsfargo.com
MS|Morgan Stanley|FIN|230|morganstanley.com
GS|Goldman Sachs|FIN|220|goldmansachs.com
AXP|American Express|FIN|210|americanexpress.com
SCHW|Charles Schwab|FIN|170|schwab.com
BLK|BlackRock|FIN|150|blackrock.com
C|Citigroup|FIN|150|citigroup.com
SPGI|S&P Global|FIN|150|spglobal.com
PGR|Progressive|FIN|130|progressive.com
COF|Capital One|FIN|120|capitalone.com
MMC|Marsh McLennan|FIN|90|marshmclennan.com
CB|Chubb|FIN|90|chubb.com
BX|Blackstone|FIN|85|blackstone.com
ICE|Intercontinental Exchange|FIN|80|ice.com
CME|CME Group|FIN|80|cmegroup.com
KKR|KKR|FIN|105|kkr.com
AON|Aon|FIN|75|aon.com
PNC|PNC Financial|FIN|75|pnc.com
USB|U.S. Bancorp|FIN|70|usbank.com
TFC|Truist Financial|FIN|60|truist.com
MCO|Moody's|FIN|85|moodys.com
AJG|Arthur J. Gallagher|FIN|70|ajg.com
TRV|Travelers|FIN|60|travelers.com
AFL|Aflac|FIN|55|aflac.com
ALL|Allstate|FIN|55|allstate.com
MET|MetLife|FIN|55|metlife.com
PRU|Prudential Financial|FIN|38|prudential.com
AIG|American International Group|FIN|45|aig.com
BK|Bank of New York Mellon|FIN|70|bny.com
STT|State Street|FIN|30|statestreet.com
DFS|Discover Financial|FIN|50|discover.com
SYF|Synchrony Financial|FIN|26|synchrony.com
FITB|Fifth Third Bancorp|FIN|28|53.com
MTB|M&T Bank|FIN|32|mtb.com
RF|Regions Financial|FIN|24|regions.com
HBAN|Huntington Bancshares|FIN|25|huntington.com
CFG|Citizens Financial|FIN|21|citizensbank.com
KEY|KeyCorp|FIN|20|key.com
NTRS|Northern Trust|FIN|23|northerntrust.com
HIG|Hartford Financial|FIN|35|thehartford.com
WTW|Willis Towers Watson|FIN|33|wtwco.com
BRO|Brown & Brown|FIN|30|bbinsurance.com
CINF|Cincinnati Financial|FIN|23|cinfin.com
L|Loews|FIN|19|loews.com
GL|Globe Life|FIN|11|globelifeinsurance.com
ERIE|Erie Indemnity|FIN|17|erieinsurance.com
MKTX|MarketAxess|FIN|7|marketaxess.com
NDAQ|Nasdaq Inc|FIN|45|nasdaq.com
CBOE|Cboe Global Markets|FIN|25|cboe.com
FDS|FactSet|FIN|15|factset.com
MSCI|MSCI|FIN|45|msci.com
TROW|T. Rowe Price|FIN|23|troweprice.com
BEN|Franklin Resources|FIN|11|franklinresources.com
IVZ|Invesco|FIN|9|invesco.com
AMP|Ameriprise Financial|FIN|50|ameriprise.com
RJF|Raymond James|FIN|32|raymondjames.com
PYPL|PayPal|FIN|55|paypal.com
FIS|Fidelity National Information|FIN|40|fisglobal.com
FI|Fiserv|FIN|85|fiserv.com
GPN|Global Payments|FIN|20|globalpayments.com
JKHY|Jack Henry|FIN|13|jackhenry.com
WRB|W. R. Berkley|FIN|27|wrberkley.com
ACGL|Arch Capital|FIN|35|archgroup.com
EG|Everest Group|FIN|14|everestglobal.com
AIZ|Assurant|FIN|10|assurant.com
PFG|Principal Financial|FIN|18|principal.com
LLY|Eli Lilly|HLTH|730|lilly.com
JNJ|Johnson & Johnson|HLTH|400|jnj.com
ABBV|AbbVie|HLTH|370|abbvie.com
UNH|UnitedHealth Group|HLTH|230|unitedhealthgroup.com
ABT|Abbott Laboratories|HLTH|230|abbott.com
MRK|Merck|HLTH|190|merck.com
TMO|Thermo Fisher Scientific|HLTH|170|thermofisher.com
ISRG|Intuitive Surgical|HLTH|160|intuitive.com
AMGN|Amgen|HLTH|140|amgen.com
BSX|Boston Scientific|HLTH|140|bostonscientific.com
SYK|Stryker|HLTH|140|stryker.com
DHR|Danaher|HLTH|130|danaher.com
GILD|Gilead Sciences|HLTH|130|gilead.com
PFE|Pfizer|HLTH|120|pfizer.com
VRTX|Vertex Pharmaceuticals|HLTH|100|vrtx.com
MDT|Medtronic|HLTH|100|medtronic.com
BMY|Bristol-Myers Squibb|HLTH|95|bms.com
ELV|Elevance Health|HLTH|75|elevancehealth.com
CI|Cigna|HLTH|80|cigna.com
CVS|CVS Health|HLTH|70|cvshealth.com
MCK|McKesson|HLTH|85|mckesson.com
COR|Cencora|HLTH|55|cencora.com
HCA|HCA Healthcare|HLTH|90|hcahealthcare.com
REGN|Regeneron|HLTH|60|regeneron.com
ZTS|Zoetis|HLTH|65|zoetis.com
BDX|Becton Dickinson|HLTH|50|bd.com
EW|Edwards Lifesciences|HLTH|45|edwards.com
A|Agilent Technologies|HLTH|35|agilent.com
IQV|IQVIA|HLTH|30|iqvia.com
IDXX|IDEXX Laboratories|HLTH|35|idexx.com
MTD|Mettler-Toledo|HLTH|25|mt.com
WAT|Waters Corporation|HLTH|21|waters.com
RMD|ResMed|HLTH|38|resmed.com
DXCM|DexCom|HLTH|30|dexcom.com
BIIB|Biogen|HLTH|20|biogen.com
MRNA|Moderna|HLTH|11|modernatx.com
CAH|Cardinal Health|HLTH|32|cardinalhealth.com
HUM|Humana|HLTH|30|humana.com
CNC|Centene|HLTH|16|centene.com
MOH|Molina Healthcare|HLTH|11|molinahealthcare.com
ZBH|Zimmer Biomet|HLTH|20|zimmerbiomet.com
STE|STERIS|HLTH|23|steris.com
BAX|Baxter International|HLTH|13|baxter.com
HOLX|Hologic|HLTH|15|hologic.com
PODD|Insulet|HLTH|21|insulet.com
ALGN|Align Technology|HLTH|11|aligntech.com
INCY|Incyte|HLTH|16|incyte.com
VTRS|Viatris|HLTH|11|viatris.com
LH|Labcorp|HLTH|21|labcorp.com
DGX|Quest Diagnostics|HLTH|21|questdiagnostics.com
CRL|Charles River Labs|HLTH|8|criver.com
TECH|Bio-Techne|HLTH|9|bio-techne.com
RVTY|Revvity|HLTH|11|revvity.com
UHS|Universal Health Services|HLTH|12|uhsinc.com
DVA|DaVita|HLTH|10|davita.com
SOLV|Solventum|HLTH|12|solventum.com
AMZN|Amazon|DISC|2300|amazon.com
TSLA|Tesla|DISC|1100|tesla.com
HD|Home Depot|DISC|390|homedepot.com
MCD|McDonald's|DISC|210|mcdonalds.com
BKNG|Booking Holdings|DISC|170|bookingholdings.com
TJX|TJX Companies|DISC|135|tjx.com
LOW|Lowe's|DISC|110|lowes.com
SBUX|Starbucks|DISC|100|starbucks.com
NKE|Nike|DISC|95|nike.com
MELI|MercadoLibre|DISC|90|mercadolibre.com
DASH|DoorDash|DISC|90|doordash.com
ABNB|Airbnb|DISC|75|airbnb.com
ORLY|O'Reilly Automotive|DISC|80|oreillyauto.com
CMG|Chipotle|DISC|55|chipotle.com
MAR|Marriott International|DISC|75|marriott.com
HLT|Hilton Worldwide|DISC|60|hilton.com
AZO|AutoZone|DISC|60|autozone.com
ROST|Ross Stores|DISC|45|rossstores.com
GM|General Motors|DISC|55|gm.com
F|Ford Motor|DISC|45|ford.com
RCL|Royal Caribbean|DISC|70|royalcaribbean.com
CCL|Carnival|DISC|30|carnival.com
NCLH|Norwegian Cruise Line|DISC|9|nclhltd.com
LVS|Las Vegas Sands|DISC|30|sands.com
MGM|MGM Resorts|DISC|9|mgmresorts.com
WYNN|Wynn Resorts|DISC|11|wynnresorts.com
DRI|Darden Restaurants|DISC|22|darden.com
YUM|Yum! Brands|DISC|40|yum.com
DPZ|Domino's Pizza|DISC|14|dominos.com
EBAY|eBay|DISC|32|ebay.com
EXPE|Expedia Group|DISC|25|expediagroup.com
TSCO|Tractor Supply|DISC|28|tractorsupply.com
ULTA|Ulta Beauty|DISC|22|ulta.com
BBY|Best Buy|DISC|16|bestbuy.com
DECK|Deckers Outdoor|DISC|16|deckers.com
LULU|Lululemon|DISC|22|lululemon.com
GRMN|Garmin|DISC|40|garmin.com
APTV|Aptiv|DISC|17|aptiv.com
LKQ|LKQ Corporation|DISC|8|lkqcorp.com
GPC|Genuine Parts|DISC|17|genpt.com
POOL|Pool Corporation|DISC|11|poolcorp.com
WSM|Williams-Sonoma|DISC|23|williams-sonoma.com
BLDR|Builders FirstSource|DISC|13|bldr.com
PHM|PulteGroup|DISC|23|pultegroup.com
DHI|D.R. Horton|DISC|45|drhorton.com
LEN|Lennar|DISC|33|lennar.com
NVR|NVR Inc|DISC|22|nvrinc.com
KMX|CarMax|DISC|7|carmax.com
CZR|Caesars Entertainment|DISC|6|caesars.com
HAS|Hasbro|DISC|10|hasbro.com
RL|Ralph Lauren|DISC|19|ralphlauren.com
TPR|Tapestry|DISC|22|tapestry.com
GOOGL|Alphabet|COMM|2400|abc.xyz
META|Meta Platforms|COMM|1800|meta.com
NFLX|Netflix|COMM|520|netflix.com
TMUS|T-Mobile US|COMM|280|t-mobile.com
DIS|Walt Disney|COMM|200|thewaltdisneycompany.com
T|AT&T|COMM|190|att.com
VZ|Verizon|COMM|170|verizon.com
CMCSA|Comcast|COMM|110|comcast.com
CHTR|Charter Communications|COMM|40|corporate.charter.com
EA|Electronic Arts|COMM|40|ea.com
TTWO|Take-Two Interactive|COMM|40|take2games.com
WBD|Warner Bros. Discovery|COMM|25|wbd.com
OMC|Omnicom Group|COMM|15|omnicomgroup.com
IPG|Interpublic Group|COMM|10|interpublic.com
LYV|Live Nation|COMM|32|livenationentertainment.com
MTCH|Match Group|COMM|8|mtch.com
PARA|Paramount Global|COMM|8|paramount.com
FOXA|Fox Corporation|COMM|25|foxcorporation.com
NWSA|News Corp|COMM|16|newscorp.com
GE|GE Aerospace|INDU|290|geaerospace.com
RTX|RTX Corporation|INDU|200|rtx.com
CAT|Caterpillar|INDU|190|caterpillar.com
UBER|Uber Technologies|INDU|180|uber.com
HON|Honeywell|INDU|130|honeywell.com
GEV|GE Vernova|INDU|130|gevernova.com
UNP|Union Pacific|INDU|120|up.com
ETN|Eaton|INDU|120|eaton.com
ADP|Automatic Data Processing|INDU|110|adp.com
BA|Boeing|INDU|150|boeing.com
DE|Deere & Company|INDU|85|deere.com
LMT|Lockheed Martin|INDU|85|lockheedmartin.com
TT|Trane Technologies|INDU|90|tranetechnologies.com
PH|Parker Hannifin|INDU|85|parker.com
GD|General Dynamics|INDU|75|gd.com
NOC|Northrop Grumman|INDU|70|northropgrumman.com
ITW|Illinois Tool Works|INDU|75|itw.com
MMM|3M|INDU|75|3m.com
EMR|Emerson Electric|INDU|70|emerson.com
CSX|CSX Corporation|INDU|60|csx.com
NSC|Norfolk Southern|INDU|60|norfolksouthern.com
FDX|FedEx|INDU|55|fedex.com
UPS|United Parcel Service|INDU|75|ups.com
CTAS|Cintas|INDU|85|cintas.com
PCAR|PACCAR|INDU|55|paccar.com
CARR|Carrier Global|INDU|55|corporate.carrier.com
JCI|Johnson Controls|INDU|60|johnsoncontrols.com
CMI|Cummins|INDU|50|cummins.com
WM|Waste Management|INDU|90|wm.com
RSG|Republic Services|INDU|70|republicservices.com
PWR|Quanta Services|INDU|55|quantaservices.com
URI|United Rentals|INDU|50|unitedrentals.com
FAST|Fastenal|INDU|45|fastenal.com
GWW|W.W. Grainger|INDU|50|grainger.com
PAYX|Paychex|INDU|50|paychex.com
VRSK|Verisk Analytics|INDU|40|verisk.com
AME|Ametek|INDU|42|ametek.com
ROK|Rockwell Automation|INDU|38|rockwellautomation.com
DOV|Dover Corporation|INDU|25|dovercorp.com
XYL|Xylem|INDU|32|xylem.com
IR|Ingersoll Rand|INDU|33|irco.com
OTIS|Otis Worldwide|INDU|38|otis.com
LHX|L3Harris|INDU|50|l3harris.com
TDG|TransDigm|INDU|75|transdigm.com
HWM|Howmet Aerospace|INDU|70|howmet.com
AXON|Axon Enterprise|INDU|55|axon.com
LDOS|Leidos|INDU|25|leidos.com
BAH|Booz Allen Hamilton|INDU|14|boozallen.com
J|Jacobs Solutions|INDU|17|jacobs.com
ACM|AECOM|INDU|15|aecom.com
MAS|Masco|INDU|14|masco.com
ALLE|Allegion|INDU|13|allegion.com
SWK|Stanley Black & Decker|INDU|11|stanleyblackanddecker.com
SNA|Snap-on|INDU|18|snapon.com
TXT|Textron|INDU|15|textron.com
HII|Huntington Ingalls|INDU|10|hii.com
EFX|Equifax|INDU|30|equifax.com
BR|Broadridge|INDU|28|broadridge.com
CPAY|Corpay|INDU|23|corpay.com
EXPD|Expeditors International|INDU|16|expeditors.com
CHRW|C.H. Robinson|INDU|14|chrobinson.com
ODFL|Old Dominion Freight|INDU|35|odfl.com
LUV|Southwest Airlines|INDU|19|southwest.com
DAL|Delta Air Lines|INDU|38|delta.com
UAL|United Airlines|INDU|32|united.com
AAL|American Airlines|INDU|8|aa.com
WMT|Walmart|STPL|780|walmart.com
COST|Costco Wholesale|STPL|420|costco.com
PG|Procter & Gamble|STPL|390|pg.com
KO|Coca-Cola|STPL|300|coca-colacompany.com
PM|Philip Morris International|STPL|250|pmi.com
PEP|PepsiCo|STPL|180|pepsico.com
MO|Altria Group|STPL|80|altria.com
MDLZ|Mondelez International|STPL|80|mondelezinternational.com
CL|Colgate-Palmolive|STPL|70|colgatepalmolive.com
TGT|Target|STPL|45|target.com
KMB|Kimberly-Clark|STPL|42|kimberly-clark.com
GIS|General Mills|STPL|28|generalmills.com
SYY|Sysco|STPL|37|sysco.com
KR|Kroger|STPL|45|kroger.com
STZ|Constellation Brands|STPL|30|cbrands.com
MNST|Monster Beverage|STPL|60|monsterbevcorp.com
KDP|Keurig Dr Pepper|STPL|45|keurigdrpepper.com
KHC|Kraft Heinz|STPL|35|kraftheinzcompany.com
HSY|Hershey|STPL|35|thehersheycompany.com
ADM|Archer-Daniels-Midland|STPL|25|adm.com
CHD|Church & Dwight|STPL|22|churchdwight.com
CLX|Clorox|STPL|15|thecloroxcompany.com
EL|Estee Lauder|STPL|30|elcompanies.com
DG|Dollar General|STPL|23|dollargeneral.com
DLTR|Dollar Tree|STPL|20|dollartree.com
TAP|Molson Coors|STPL|10|molsoncoors.com
BG|Bunge Global|STPL|12|bunge.com
CAG|Conagra Brands|STPL|9|conagrabrands.com
CPB|Campbell's|STPL|10|campbells.com
HRL|Hormel Foods|STPL|15|hormelfoods.com
K|Kellanova|STPL|28|kellanova.com
SJM|J.M. Smucker|STPL|11|jmsmucker.com
MKC|McCormick|STPL|19|mccormick.com
LW|Lamb Weston|STPL|8|lambweston.com
TSN|Tyson Foods|STPL|20|tysonfoods.com
WBA|Walgreens Boots Alliance|STPL|10|walgreensbootsalliance.com
XOM|Exxon Mobil|ENRG|470|exxonmobil.com
CVX|Chevron|ENRG|300|chevron.com
COP|ConocoPhillips|ENRG|120|conocophillips.com
EOG|EOG Resources|ENRG|65|eogresources.com
SLB|SLB|ENRG|55|slb.com
PSX|Phillips 66|ENRG|50|phillips66.com
MPC|Marathon Petroleum|ENRG|50|marathonpetroleum.com
WMB|Williams Companies|ENRG|70|williams.com
KMI|Kinder Morgan|ENRG|60|kindermorgan.com
OKE|ONEOK|ENRG|50|oneok.com
VLO|Valero Energy|ENRG|42|valero.com
OXY|Occidental Petroleum|ENRG|45|oxy.com
HES|Hess|ENRG|45|hess.com
BKR|Baker Hughes|ENRG|45|bakerhughes.com
HAL|Halliburton|ENRG|21|halliburton.com
DVN|Devon Energy|ENRG|22|devonenergy.com
FANG|Diamondback Energy|ENRG|45|diamondbackenergy.com
CTRA|Coterra Energy|ENRG|19|coterra.com
EQT|EQT Corporation|ENRG|30|eqt.com
TRGP|Targa Resources|ENRG|38|targaresources.com
EXE|Expand Energy|ENRG|25|expandenergy.com
TPL|Texas Pacific Land|ENRG|25|texaspacific.com
NEE|NextEra Energy|UTIL|140|nexteraenergy.com
SO|Southern Company|UTIL|85|southerncompany.com
DUK|Duke Energy|UTIL|80|duke-energy.com
CEG|Constellation Energy|UTIL|80|constellationenergy.com
AEP|American Electric Power|UTIL|55|aep.com
D|Dominion Energy|UTIL|50|dominionenergy.com
SRE|Sempra|UTIL|55|sempra.com
VST|Vistra|UTIL|55|vistracorp.com
PEG|Public Service Enterprise|UTIL|42|pseg.com
EXC|Exelon|UTIL|45|exeloncorp.com
XEL|Xcel Energy|UTIL|42|xcelenergy.com
ED|Consolidated Edison|UTIL|35|conedison.com
WEC|WEC Energy Group|UTIL|33|wecenergygroup.com
ETR|Entergy|UTIL|38|entergy.com
AEE|Ameren|UTIL|26|ameren.com
DTE|DTE Energy|UTIL|28|dteenergy.com
PPL|PPL Corporation|UTIL|26|pplweb.com
FE|FirstEnergy|UTIL|24|firstenergycorp.com
CMS|CMS Energy|UTIL|21|cmsenergy.com
CNP|CenterPoint Energy|UTIL|24|centerpointenergy.com
NRG|NRG Energy|UTIL|30|nrg.com
ATO|Atmos Energy|UTIL|24|atmosenergy.com
NI|NiSource|UTIL|20|nisource.com
LNT|Alliant Energy|UTIL|16|alliantenergy.com
EVRG|Evergy|UTIL|16|evergy.com
ES|Eversource Energy|UTIL|23|eversource.com
AES|AES Corporation|UTIL|9|aes.com
PNW|Pinnacle West|UTIL|11|pinnaclewest.com
LIN|Linde|MATL|220|linde.com
SHW|Sherwin-Williams|MATL|75|sherwin-williams.com
ECL|Ecolab|MATL|65|ecolab.com
APD|Air Products|MATL|60|airproducts.com
FCX|Freeport-McMoRan|MATL|60|fcx.com
NEM|Newmont|MATL|60|newmont.com
CRH|CRH|MATL|70|crh.com
VMC|Vulcan Materials|MATL|35|vulcanmaterials.com
MLM|Martin Marietta|MATL|33|martinmarietta.com
NUE|Nucor|MATL|32|nucor.com
STLD|Steel Dynamics|MATL|21|steeldynamics.com
DOW|Dow Inc|MATL|20|dow.com
LYB|LyondellBasell|MATL|18|lyondellbasell.com
PPG|PPG Industries|MATL|25|ppg.com
DD|DuPont|MATL|30|dupont.com
IFF|International Flavors|MATL|19|iff.com
ALB|Albemarle|MATL|11|albemarle.com
CE|Celanese|MATL|6|celanese.com
MOS|Mosaic|MATL|9|mosaicco.com
CF|CF Industries|MATL|14|cfindustries.com
IP|International Paper|MATL|26|internationalpaper.com
PKG|Packaging Corp of America|MATL|20|packagingcorp.com
AMCR|Amcor|MATL|14|amcor.com
BALL|Ball Corporation|MATL|16|ball.com
AVY|Avery Dennison|MATL|14|averydennison.com
SW|Smurfit Westrock|MATL|23|smurfitwestrock.com
PLD|Prologis|REAL|80|prologis.com
AMT|American Tower|REAL|90|americantower.com
EQIX|Equinix|REAL|75|equinix.com
WELL|Welltower|REAL|95|welltower.com
SPG|Simon Property Group|REAL|55|simon.com
O|Realty Income|REAL|50|realtyincome.com
PSA|Public Storage|REAL|50|publicstorage.com
CCI|Crown Castle|REAL|42|crowncastle.com
DLR|Digital Realty|REAL|55|digitalrealty.com
CBRE|CBRE Group|REAL|40|cbre.com
EXR|Extra Space Storage|REAL|31|extraspace.com
AVB|AvalonBay Communities|REAL|28|avaloncommunities.com
EQR|Equity Residential|REAL|26|equityapartments.com
VTR|Ventas|REAL|28|ventasreit.com
INVH|Invitation Homes|REAL|20|invitationhomes.com
MAA|Mid-America Apartment|REAL|17|maac.com
ESS|Essex Property Trust|REAL|18|essex.com
UDR|UDR Inc|REAL|14|udr.com
ARE|Alexandria Real Estate|REAL|13|are.com
IRM|Iron Mountain|REAL|28|ironmountain.com
WY|Weyerhaeuser|REAL|19|weyerhaeuser.com
HST|Host Hotels & Resorts|REAL|11|hosthotels.com
KIM|Kimco Realty|REAL|14|kimcorealty.com
REG|Regency Centers|REAL|13|regencycenters.com
FRT|Federal Realty|REAL|8|federalrealty.com
BXP|BXP Inc|REAL|11|bxp.com
DOC|Healthpeak Properties|REAL|13|healthpeak.com
CPT|Camden Property Trust|REAL|12|camdenliving.com
CSGP|CoStar Group|REAL|30|costargroup.com
WSO|Watsco|INDU|15|watsco.com
FTV|Fortive|INDU|18|fortive.com
EMN|Eastman Chemical|MATL|8|eastman.com
NDSN|Nordson|INDU|12|nordson.com
PNR|Pentair|INDU|17|pentair.com
GNRC|Generac|INDU|10|generac.com
AOS|A. O. Smith|INDU|10|aosmith.com
ROL|Rollins|INDU|27|rollins.com
CHE|Chemed|HLTH|7|chemed.com
HSIC|Henry Schein|HLTH|8|henryschein.com
COO|Cooper Companies|HLTH|14|coopercos.com
XRAY|Dentsply Sirona|HLTH|3|dentsplysirona.com
JBHT|J.B. Hunt|INDU|14|jbhunt.com
LII|Lennox International|INDU|21|lennox.com
BRBR|BellRing Brands|STPL|9|bellring.com
COKE|Coca-Cola Consolidated|STPL|11|cokeconsolidated.com
WRK|Smurfit WestRock Partners|MATL|8|westrock.com
CTVA|Corteva|MATL|45|corteva.com
FMC|FMC Corporation|MATL|5|fmc.com
VLTO|Veralto|INDU|26|veralto.com
TKO|TKO Group|COMM|14|tkogrp.com
APO|Apollo Global Management|FIN|80|apollo.com
ARES|Ares Management|FIN|55|aresmgmt.com
COIN|Coinbase|FIN|75|coinbase.com
HOOD|Robinhood Markets|FIN|60|robinhood.com
CPRT|Copart|INDU|55|copart.com
WST|West Pharmaceutical|HLTH|17|westpharma.com
"""


def _parse(raw):
    out = []
    for line in raw.strip().split('\n'):
        parts = line.split('|')
        if len(parts) != 5:
            continue
        ticker, name, sector, cap, domain = parts
        out.append({'ticker': ticker, 'name': name,
                    'sector': SECTOR_NAMES.get(sector, sector),
                    'cap': float(cap), 'domain': domain})
    return out


SP500 = _parse(_SP500_RAW)

# The Nasdaq-100 is non-financial and Nasdaq-listed; this is its overlap with
# the table above plus the names that are not in the S&P 500.
NASDAQ100_TICKERS = [
    'NVDA', 'MSFT', 'AAPL', 'AMZN', 'AVGO', 'META', 'GOOGL', 'TSLA', 'NFLX',
    'COST', 'PLTR', 'AMD', 'TMUS', 'CSCO', 'INTU', 'TXN', 'QCOM', 'AMGN',
    'ISRG', 'BKNG', 'ADBE', 'HON', 'AMAT', 'PANW', 'ADP', 'GILD', 'VRTX',
    'MU', 'LRCX', 'ADI', 'MELI', 'KLAC', 'SBUX', 'INTC', 'CRWD', 'MDLZ',
    'CTAS', 'CEG', 'ORLY', 'ABNB', 'CDNS', 'SNPS', 'MAR', 'MRVL', 'FTNT',
    'PYPL', 'DASH', 'ADSK', 'MNST', 'WDAY', 'NXPI', 'ROP', 'AEP', 'CHTR',
    'PCAR', 'PAYX', 'KDP', 'ROST', 'FAST', 'ODFL', 'EXC', 'VRSK', 'XEL',
    'EA', 'CTSH', 'KHC', 'IDXX', 'TTWO', 'DXCM', 'CSGP', 'ANSS', 'ON',
    'CDW', 'BIIB', 'GEHC', 'TTD', 'DDOG', 'TEAM', 'ZS', 'ARM', 'LIN',
    'APP', 'AXON', 'MSTR', 'LULU', 'CCEP', 'TSCO', 'GFS', 'WBD', 'ALGN',
    'ILMN', 'SMCI', 'MDB', 'ENPH', 'JD', 'PDD', 'BIDU', 'NTES', 'ATVI',
    'SIRI',
]

# Names in the Nasdaq-100 that the S&P 500 table does not carry.
_EXTRA = _parse("""\
GEHC|GE HealthCare|HLTH|38|gehealthcare.com
TTD|The Trade Desk|TECH|30|thetradedesk.com
DDOG|Datadog|TECH|45|datadoghq.com
TEAM|Atlassian|TECH|50|atlassian.com
ZS|Zscaler|TECH|35|zscaler.com
ARM|Arm Holdings|TECH|140|arm.com
MSTR|Strategy|TECH|60|strategy.com
CCEP|Coca-Cola Europacific|STPL|38|cocacolaep.com
GFS|GlobalFoundries|TECH|20|gf.com
ILMN|Illumina|HLTH|16|illumina.com
MDB|MongoDB|TECH|22|mongodb.com
PDD|PDD Holdings|DISC|140|pddholdings.com
JD|JD.com|DISC|45|jd.com
BIDU|Baidu|COMM|32|baidu.com
NTES|NetEase|COMM|65|netease.com
SIRI|Sirius XM|COMM|8|siriusxm.com
""")

_BY_TICKER = {c['ticker']: c for c in SP500 + _EXTRA}


def constituents(index='sp500'):
    """The index members, largest first."""
    if index.lower() in ('ndx', 'nasdaq100', 'nasdaq', 'nasdaq-100'):
        rows = [_BY_TICKER[t] for t in NASDAQ100_TICKERS if t in _BY_TICKER]
    else:
        rows = list(SP500)
    return sorted(rows, key=lambda c: -c['cap'])


# ------------------------------------------------------- 2. batch quotes ---

_CRUMB = {'value': None, 'cookies': None, 'at': 0}


def _crumb():
    """Yahoo's v7 quote endpoint wants a cookie plus a crumb. Fetched once an
    hour; a failure here is not fatal because the caller falls back."""
    if _CRUMB['value'] and time.time() - _CRUMB['at'] < 3600:
        return _CRUMB['value'], _CRUMB['cookies']
    try:
        s = requests.Session()
        s.get('https://fc.yahoo.com', headers=HEADERS, timeout=8)
        r = s.get('https://query2.finance.yahoo.com/v1/test/getcrumb',
                  headers=HEADERS, timeout=8)
        if r.ok and r.text and len(r.text) < 40:
            _CRUMB.update(value=r.text.strip(), cookies=s.cookies, at=time.time())
            return _CRUMB['value'], _CRUMB['cookies']
    except Exception:
        pass
    return None, None


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _quotes_v7(tickers):
    crumb, cookies = _crumb()
    if not crumb:
        return {}
    out = {}
    for group in _chunks(tickers, 50):
        try:
            r = requests.get('https://query2.finance.yahoo.com/v7/finance/quote',
                             headers=HEADERS, cookies=cookies, timeout=12,
                             params={'symbols': ','.join(group), 'crumb': crumb})
            if not r.ok:
                continue
            for q in r.json().get('quoteResponse', {}).get('result', []):
                sym = q.get('symbol')
                price = q.get('regularMarketPrice')
                if not sym or price is None:
                    continue
                out[sym] = {
                    'price': round(float(price), 2),
                    'chg': round(float(q.get('regularMarketChangePercent') or 0), 2),
                    'cap': (float(q['marketCap']) / 1e9) if q.get('marketCap') else None,
                    'open': q.get('regularMarketOpen'),
                    'prev_close': q.get('regularMarketPreviousClose'),
                    'volume': q.get('regularMarketVolume'),
                    'name': q.get('shortName') or q.get('longName'),
                }
        except Exception:
            continue
    return out


def _quotes_spark(tickers):
    """Fallback: the spark endpoint takes many symbols and needs no crumb."""
    out = {}
    for group in _chunks(tickers, 50):
        try:
            r = requests.get('https://query1.finance.yahoo.com/v8/finance/spark',
                             headers=HEADERS, timeout=12,
                             params={'symbols': ','.join(group),
                                     'range': '5d', 'interval': '1d'})
            if not r.ok:
                continue
            data = r.json()
            items = data.get('spark', {}).get('result', data) if isinstance(data, dict) else {}
            if isinstance(items, dict):
                items = [{'symbol': k, 'response': [v]} for k, v in items.items()]
            for it in items or []:
                sym = it.get('symbol')
                resp = (it.get('response') or [{}])[0]
                closes = [c for c in ((resp.get('indicators', {})
                          .get('quote', [{}])[0].get('close')) or []) if c is not None]
                meta = resp.get('meta', {})
                if not sym or len(closes) < 2:
                    continue
                price, prev = float(closes[-1]), float(closes[-2])
                out[sym] = {'price': round(price, 2),
                            'chg': round((price - prev) / prev * 100, 2) if prev else 0.0,
                            'cap': None, 'open': None,
                            'prev_close': round(prev, 2), 'volume': None, 'name': None}
        except Exception:
            continue
    return out


def batch_quotes(tickers, per_ticker_fallback=None):
    """Live price, change and market cap for many symbols at once.

    Tries the batch endpoints first; whatever they miss is filled in by the
    caller's per-ticker function, which is the slow path and so is used only
    for the remainder.
    """
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    out = _quotes_v7(tickers)
    missing = [t for t in tickers if t not in out]
    if missing:
        out.update(_quotes_spark(missing))
    missing = [t for t in tickers if t not in out]
    if missing and per_ticker_fallback:
        with ThreadPoolExecutor(max_workers=16) as ex:
            for t, q in zip(missing, ex.map(per_ticker_fallback, missing)):
                if q and q.get('price') is not None:
                    out[t] = {'price': q['price'], 'chg': q.get('chg'), 'cap': None,
                              'open': None, 'prev_close': None, 'volume': None,
                              'name': None}
    return out


# --------------------------------------------------- 3. CNN Fear & Greed ---

CNN_URL = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'

RATINGS = [
    (25, 'Extreme Fear'), (45, 'Fear'), (55, 'Neutral'),
    (75, 'Greed'), (101, 'Extreme Greed'),
]


def rating_for(score):
    for ceiling, label in RATINGS:
        if score < ceiling:
            return label
    return 'Extreme Greed'


# CNN's own labels for the seven inputs it combines.
COMPONENTS = [
    ('market_momentum_sp500', 'Market Momentum', 'S&P 500 vs its 125-day average'),
    ('stock_price_strength', 'Stock Price Strength', 'Net new 52-week highs on the NYSE'),
    ('stock_price_breadth', 'Stock Price Breadth', 'Volume in advancing vs declining stocks'),
    ('put_call_options', 'Put and Call Options', '5-day average put/call ratio'),
    ('market_volatility_vix', 'Market Volatility', 'VIX vs its 50-day average'),
    ('safe_haven_demand', 'Safe Haven Demand', 'Stock returns vs Treasury returns'),
    ('junk_bond_demand', 'Junk Bond Demand', 'Yield spread, junk vs investment grade'),
]


def fear_greed():
    """CNN's published index. Returns ok=False rather than inventing a number:
    a made-up sentiment reading is worse than an empty panel."""
    def build():
        try:
            r = requests.get(CNN_URL, headers=HEADERS, timeout=12)
            if not r.ok:
                return {'ok': False, 'error': f'CNN returned HTTP {r.status_code}'}
            data = r.json()
        except Exception as e:
            return {'ok': False, 'error': f'Could not reach CNN ({type(e).__name__})'}

        fg = data.get('fear_and_greed') or {}
        score = fg.get('score')
        if score is None:
            return {'ok': False, 'error': 'CNN response did not contain a score'}
        score = round(float(score))

        def prev(key):
            v = fg.get(key)
            return round(float(v)) if v is not None else None

        comps = []
        for key, label, blurb in COMPONENTS:
            node = data.get(key) or {}
            v = node.get('score')
            if v is None:
                continue
            comps.append({
                'key': key, 'label': label, 'blurb': blurb,
                'score': round(float(v)),
                'rating': node.get('rating') or rating_for(float(v)),
            })

        history = []
        for p in (fg.get('historical') or data.get('fear_and_greed_historical', {}).get('data') or [])[-90:]:
            if isinstance(p, dict) and p.get('y') is not None:
                history.append(round(float(p['y']), 1))

        return {
            'ok': True,
            'score': score,
            'rating': fg.get('rating') or rating_for(score),
            'updated': fg.get('timestamp'),
            'previous': {
                'close': prev('previous_close'),
                'week': prev('previous_1_week'),
                'month': prev('previous_1_month'),
                'year': prev('previous_1_year'),
            },
            'components': comps,
            'history': history,
            'source': 'CNN Business Fear & Greed Index',
        }

    return _cached('fg', 900, build)
