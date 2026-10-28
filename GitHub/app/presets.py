"""Named snapshots of the boss library; runtime timers never enter presets."""
import copy,re,uuid

def save_preset(config,name,color):
    name=name.strip()
    if not name:raise ValueError('Enter a preset name.')
    if len(name)>60:raise ValueError('Keep the preset name within 60 characters.')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Choose a valid color.')
    presets=config.setdefault('presets',[])
    if any(p['name'].casefold()==name.casefold() for p in presets):raise ValueError('A preset with this name already exists.')
    preset=dict(id=uuid.uuid4().hex,name=name,color=color,bosses=copy.deepcopy(config['bosses']))
    presets.append(preset)
    return preset

def merged_library(current,preset):
    # Entries added since saving stay available, unpinned. A preset can restore
    # an accidentally deleted entry without discarding the rest of the library.
    result=copy.deepcopy(current);by_id={e['id']:e for e in result}
    for entry in result:entry['pinned']=False
    for saved in preset['bosses']:
        if saved['id'] in by_id:by_id[saved['id']].update(copy.deepcopy(saved))
        else:result.append(copy.deepcopy(saved))
    from storage import validate
    validate(dict(bosses=result,ui_scale=1,scale=1,opacity=.9,visible_rows=3))
    return result
