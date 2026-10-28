"""Reproduce anonymous official LAMOST SQL checks used for source validation."""
import argparse,urllib.request,urllib.parse,http.cookiejar,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='https://www.lamost.org/dr10/v2.0/'
FEATURES=['mag_ps_g','mag_ps_r','mag_ps_i','mag_ps_z','mag_ps_y','gaia_g_mean_mag']
VALID=' AND '.join(f'{c} BETWEEN -30 AND 50' for c in FEATURES)
LABEL="CASE WHEN class='GALAXY' THEN 'GALAXY' WHEN class='QSO' THEN 'QSO' WHEN class='STAR' AND (subclass LIKE 'dM%' OR subclass LIKE 'gM%' OR subclass LIKE 'sdM%' OR subclass LIKE 'M%') THEN 'M' WHEN class='STAR' AND left(subclass,1) IN ('A','F','G','K') THEN left(subclass,1) ELSE 'OTHER' END"
def query(sql,fmt='json'):
    o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    html=o.open(BASE+'sql',timeout=30).read().decode()
    data={'sql':sql,'output.fmt':fmt}
    for tag in re.findall(r'<input[^>]*>',html):
        if 'csrf_token' in tag:
            value=re.search(r'value=[\"\x27]([^\"\x27]+)',tag)
            if value:data['csrf_token']=value.group(1)
    req=urllib.request.Request(BASE+'sql/q',data=urllib.parse.urlencode(data).encode(),headers={'Referer':BASE+'sql'})
    with o.open(req,timeout=120) as r:return r.read()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('check',choices=['pilot','zero-probe','aggregate']);args=parser.parse_args()
    if args.check=='pilot':
        sql=f'SELECT obsid,uid,gaia_source_id,ps_id,class,subclass,snri,{",".join(FEATURES)},ra,dec,planid,mjd FROM catalogue WHERE {VALID} LIMIT 10000'
        path=ROOT/'raw/query_speed_preview.csv';fmt='csv'
    elif args.check=='zero-probe':
        sql='SELECT obsid,uid,ps_id,mag_ps_g,mag_ps_r,mag_ps_i,mag_ps_z,mag_ps_y,gaia_source_id,gaia_g_mean_mag FROM catalogue WHERE obsid IN (15803104,15803108,15803113,15803133,15803135,15803138,15803204,15803213,15804032,15804038,15804042) LIMIT 20'
        path=ROOT/'audit/official_zero_probe.json';fmt='json'
    else:
        sql=f"WITH labelled AS (SELECT uid,{LABEL} target FROM catalogue WHERE {VALID} AND uid IS NOT NULL AND uid<>''), sources AS (SELECT uid,min(target) target,count(DISTINCT target) n_labels,count(*) n_spectra FROM labelled WHERE target<>'OTHER' GROUP BY uid) SELECT CASE WHEN n_labels=1 THEN target ELSE 'AMBIGUOUS' END target,count(*) n_unique_sources,sum(n_spectra) n_spectra FROM sources GROUP BY CASE WHEN n_labels=1 THEN target ELSE 'AMBIGUOUS' END ORDER BY n_unique_sources DESC LIMIT 20"
        path=ROOT/'audit/official_complete_case_counts.json';fmt='json'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(query(sql,fmt));print(path)
if __name__=='__main__':main()
