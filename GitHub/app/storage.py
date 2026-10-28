"""Versioned, atomic configuration storage with non-destructive legacy import."""
import copy
import json
import os
from pathlib import Path
import shutil
import uuid
import sys
from boss_rules import enrich, normalized, VERSION

DEFAULT_BOSSES = [
    dict(id='jade', name='Qiongyu, the White-Jade Dragon', duration=900, color='#f4f1eb', pinned=True, mechanic='standard'),
    dict(id='bow', name='Ye Wuxian, the Stringless Bow', duration=900, color='#d7b6f5', pinned=True, mechanic='standard'),
    dict(id='kraken', name='Old Thunder, the Stormcliff Kraken', duration=480, color='#a8d6ff', pinned=True, mechanic='kraken'),
    dict(id='roc', name='The Roc Matriarch', duration=None, color='#d9e8bf', pinned=False, mechanic='standard'),
    dict(id='tianma', name='Tianma', duration=None, color='#f4c6dc', pinned=False, mechanic='standard'),
    dict(id='wuyan', name='Wuyan, the Unsated Heart', duration=None, color='#e6b9af', pinned=False, mechanic='standard'),
    dict(id='warden', name='The Stair-Bell Warden', duration=None, color='#c9d9e6', pinned=False, mechanic='standard'),
]


def migrate(data):
    """Expand old settings without discarding unknown fields or existing records."""
    result = copy.deepcopy(data)
    if 'bosses' not in result:
        result['bosses'] = copy.deepcopy(DEFAULT_BOSSES)
        for boss in result['bosses']:
            boss['duration'] = result.get('durations', {}).get(boss['id'], boss['duration'])
    result.setdefault('scale', .82)
    result.setdefault('opacity', .9)
    result.setdefault('theme_opacity', .84)
    result.setdefault('visible_rows', 3)
    result.setdefault('width_units', None)
    result.setdefault('timers', {})
    result.setdefault('qi', {})
    result.setdefault('events', {})
    result.setdefault('windows', {})
    result.setdefault('ui_opacity', .95)
    result.setdefault('ui_scale', 1.)
    result.setdefault('reference_windows', {})
    result.setdefault('presets',[])
    result.setdefault('deleted_boss_ids',[])
    if 'wukong' not in result['deleted_boss_ids'] and not any('yu wukuang' in normalized(e['name']) or 'wukong' in normalized(e['name']) for e in result['bosses']):
        result['bosses'].append(dict(id='wukong',name='Yu Wukuang, the Mad Jade Disciple',alias='Wukong',duration=None,color='#a8edaa',pinned=False,mechanic='wukong'))
    enrich(result['bosses'])
    result['release_version']=VERSION
    result['schema_version'] = 8
    validate(result)
    return result


def validate(data):
    if not .5<=float(data.get('ui_scale',1))<=1:raise ValueError('UI scale must be 50–100%.')
    if not isinstance(data.get('bosses'), list):
        raise ValueError('The saved boss list is invalid; it was not overwritten.')
    ids, names = set(), set()
    for boss in data['bosses']:
        if not isinstance(boss, dict) or not isinstance(boss.get('name'), str) or not boss['name'].strip():
            raise ValueError('A saved boss name is invalid; the file was preserved.')
        boss.setdefault('id', uuid.uuid4().hex)
        boss.setdefault('pinned', False)
        boss.setdefault('color', '#d4dbe5')
        boss.setdefault('duration', None)
        boss.setdefault('alias', '')
        boss.setdefault('alias_override', False)
        if not isinstance(boss['alias'],str): raise ValueError('Invalid saved alias.')
        boss.setdefault('mechanic', 'standard')
        if boss['id'] in ids or boss['name'].casefold() in names:
            raise ValueError('Duplicate saved boss entries need to be corrected.')
        ids.add(boss['id']); names.add(boss['name'].casefold())
        if boss['duration'] is not None and not 1 <= boss['duration'] <= 86400:
            raise ValueError('A saved respawn duration is invalid.')
    if not .5 <= float(data['scale']) <= 2.0 or not .45 <= float(data['opacity']) <= 1:
        raise ValueError('Saved size or transparency is outside its valid range.')
    if not .45 <= float(data.get('theme_opacity',.84)) <= 1:
        raise ValueError('Invalid theme transparency.')
    if data.get('width_units') is not None:
        data['width_units']=max(1,float(data['width_units']))
    data['visible_rows'] = max(1, float(data['visible_rows']))


def bundled_catalog():
    resource_root=Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return json.loads((resource_root/'data'/'bosses.json').read_text(encoding='utf-8'))


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder/'settings.json'
        source = self.path if self.path.exists() else None
        raw = json.loads(source.read_text(encoding='utf-8-sig')) if source else {'bosses': bundled_catalog()}
        self.data = migrate(raw)
        if source:
            backup = self.folder/'settings.before-tracker.json'
            if not backup.exists():
                shutil.copy2(source, backup)
        self.save()

    def save(self):
        validate(self.data)
        temp = self.path.with_suffix('.json.tmp')
        with temp.open('w', encoding='utf-8') as file:
            json.dump(self.data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, self.path)
