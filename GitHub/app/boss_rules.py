"""Regional boss assignments and supported announcement variants."""
import unicodedata
VERSION = 'V1.3.1'
REGIONS = ('Region 1 — Central Plains', 'Region 2 — West Region', 'Region 2.5 — Ninth Chain', 'Region 3 — Past the Ninth Gate', 'Unassigned')
def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold()
R1 = ('mo qingshan', 'abbot wuxin', 'nameless general', 'black tiger king', 'lei wuji', 'old scarback', 'red sail mao', 'grey fang', 'crimson moon priestess', 'crimson priestess', 'iron-beak hou', 'foreman gou', 'sword wraith')
R25 = ('cinder-mane', 'fen zhao', 'grey pilgrim', 'lu jiugong', 'marshal tie yan', 'lei zhen', 'mo xuanying', 'gao shun', 'bonewrath', 'sad cultivator')
R3 = ('herald of guixu', 'patriarch lou kunshan', 'ye wuxian', 'stair-bell warden', 'warden-colossus of the maw', 'qiongyu', 'stormcliff kraken')
R2 = ('old scar ma', 'qara ashina', 'jingzhe', 'old thunderhoof', 'tianma', 'roc matriarch', 'magistrate yan shou', 'blind jiao', 'khan temur', 'hu yaoji', 'suanni', 'kulong', 'kang bai', 'gu wuyan', 'fan yi', 'star-iron warden', 'lan wuhen', 'sleeping colossus', 'yu wukuang', 'wukong', 'wuyan,', 'yu lian')
def region_for(name):
    name = normalized(name)
    if name.startswith('jiao,'): return REGIONS[0]
    for needles, region in ((R3,REGIONS[3]),(R25,REGIONS[2]),(R1,REGIONS[0]),(R2,REGIONS[1])):
        if any(n in name for n in needles): return region
    return REGIONS[4]
def enrich(entries):
    for entry in entries:
        name = normalized(entry['name'])
        entry.setdefault('region',region_for(name))
        if 'sleeping colossus' in name: entry['mechanic']='colossus'
        elif 'sword wraith' in name: entry['mechanic']='sword'
        elif 'yu wukuang' in name or name=='wukong': entry['mechanic']='wukong'
    return entries
SPECIAL_KILLS=(
 ('qiongyu',('qiongyu sinks back into its spring','water goes still and clear')),
 ('patriarch lou kunshan',('on the veinwind spire the patriarch falls','veins of the whole spire stop')),
 ('stair-bell warden',('stair-bell warden falls silent','stair under it stands open')),
 ('ye wuxian',('lowers the bow that has no string','grey goes out of the seam')),
 ('warden-colossus',('warden-colossus goes down on its knees','jade light goes out')),
 ('lu jiugong',('at the shattered array','nine steles go dark')),
 ('bonewrath',('bonewrath falls apart','violet fire in its skull goes out')),
 ('marshal tie yan',('marshal tie yan goes down on one knee','burnt host gutters out')),
 ('sad cultivator',('sad cultivator has laid down his sword','burial bell has rung')),
 ('suanni',('suanni unravels into smoke','incense goes quiet')),
 ('sleeping colossus',('subdued the sleeping colossus','made its seals whole again')),
 ('sleeping colossus',('the chained one falls to its knees','chains drag it home')),
 ('yu wukuang',('struck down yu wukuang','burst into jade dust')),
)
SPECIAL_SPAWNS=(
 ('kulong',('dead riverbed stirs','kulong','has risen')),
 ('tianma',('tianma','thunder stallion','is running again')),
 ('mo qingshan',('mo qingshan','stirs in ashen hollow')),
 ('sleeping colossus',('sleeping colossus has woken','sealed crater')),
 ('yu wukuang',('a giant of jade has come down','his pressure lies over')),
)
def special_events(text,entries):
    text=' '.join(normalized(text).split())
    for kind,rules in (('killed',SPECIAL_KILLS),('spawned',SPECIAL_SPAWNS)):
        for owner,clauses in rules:
            if all(clause in text for clause in clauses):
                matches=[e['id'] for e in entries if owner in normalized(e['name']) or (owner=='yu wukuang' and e.get('mechanic')=='wukong')]
                if len(matches)==1: yield matches[0],kind
