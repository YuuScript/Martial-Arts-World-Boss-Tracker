"""Index searching and collision checks shared by UI and tests."""
import re


def names(entry):
    return [entry['name']]+[n.strip() for n in entry.get('alias','').split(';') if n.strip()]


def normalized(name):return ''.join(re.findall(r'[a-z0-9]+',name.casefold()))


def recognized_names(entry):
    result=names(entry)
    prefix=entry['name'].split(',')[0].strip()
    if ',' in entry['name'] and len(normalized(prefix))>=4:result.append(prefix)
    return result


def alias_warnings(candidate,entries):
    warnings=[]
    for other in entries:
        if candidate.get('id')==other['id']:continue
        for alias in names(candidate)[1:]:
            phrase=' '.join(re.findall(r'[a-z0-9]+',alias.casefold()))
            for alternative in recognized_names(other):
                full=' '.join(re.findall(r'[a-z0-9]+',alternative.casefold()))
                if normalized(alias)==normalized(alternative) or re.search(r'(?<![a-z0-9])'+re.escape(phrase)+r'(?![a-z0-9])',full):
                    warnings.append(f'"{alias}" also appears in {other["name"]}. You can still save; enable alias priority if needed.');break
    return warnings


def check_name_conflicts(candidate,entries):
    if any(len(normalized(n))<2 for n in names(candidate)):raise ValueError('Names and aliases need at least two letters or digits.')
    for other in entries:
        if candidate.get('id')!=other['id'] and normalized(candidate['name'])==normalized(other['name']):
            raise ValueError(f'A boss with this full name already exists: {other["name"]}')
    return alias_warnings(candidate,entries)


def filtered_entries(entries,query):
    key=normalized(query)
    return sorted((entry for entry in entries if not key or any(key in normalized(n) for n in names(entry))),key=lambda e:(not e['pinned'],e['name'].casefold()))
