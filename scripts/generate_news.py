import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_KEY = os.environ.get('GNEWS_API_KEY', '').strip()
OUTPUT_PATH = 'data/news.json'

MAX_ITEMS = 10           # máximo en el JSON
MIN_ITEMS = 5            # mínimo que queremos mostrar siempre
CUTOFF_HOURS = 24 * 7    # ventana: últimos 7 días
MAX_AST_ITEMS = 4
MIN_DIVERSITY_ITEMS = 2
DIVERSITY_TAGS = {'Starlink', 'Skylo', 'Android', 'iOS', 'MNO', 'D2C', 'Chipset', '3GPP'}

# Consultas centradas en AST, D2C, Starlink, Skylo, MNOs, Android/iOS, 3GPP
queries = [
    'AST SpaceMobile OR BlueBird OR ASTS',
    '"direct-to-cell" OR D2C OR "direct to cell" OR satellite-to-cell',
    'Starlink AND satellite AND operator',
    'Skylo OR NTN OR "non-terrestrial network"',
    '"Android satellite" OR SatMode OR "iOS satellite" OR Globalstar',
    'Vodafone OR AT&T OR Verizon OR Orange OR Rakuten OR Rogers OR Optus OR KDDI satellite'
]

# Boost por fuente
source_boost = {
    'spacenews': 20,
    'satellite today': 18,
    'via satellite': 18,
    'light reading': 18,
    'rcr wireless': 16,
    'satnews': 16,
    'telecomtv': 16,
    'skylo': 10,
    'ast spacemobile': 10,
    'starlink': 10,
}

# Reglas de scoring por tema
keyword_rules = [
    {'tag': 'MNO', 'badge': 'Operator Strategy', 'weight': 30, 'patterns': ['mno', 'operator', 'vodafone', 'orange', 'at&t', 'verizon', 't-mobile', 'rakuten', 'rogers', 'optus', 'kddi']},
    {'tag': 'D2C', 'badge': 'Direct-to-Cell', 'weight': 28, 'patterns': ['direct-to-cell', 'direct to cell', 'd2c', 'satellite-to-cell']},
    {'tag': 'Starlink', 'badge': 'Starlink', 'weight': 24, 'patterns': ['starlink', 'spacex']},
    {'tag': 'Skylo', 'badge': 'Skylo / NTN', 'weight': 22, 'patterns': ['skylo', 'ntn', 'non-terrestrial network', 'nb-iot ntn']},
    {'tag': 'AST', 'badge': 'AST / D2C', 'weight': 20, 'patterns': ['ast spacemobile', 'asts', 'bluebird']},
    {'tag': 'Android', 'badge': 'Android / SatMode', 'weight': 14, 'patterns': ['android', 'satmode', 'pixel']},
    {'tag': 'iOS', 'badge': 'iOS / Satellite', 'weight': 14, 'patterns': ['ios', 'iphone', 'apple satellite', 'globalstar']},
    {'tag': 'Chipset', 'badge': 'Chipset / RF', 'weight': 12, 'patterns': ['qualcomm', 'mediatek', 'modem', 'chipset', 'x85', 'x80', 'm90']},
    {'tag': '3GPP', 'badge': '3GPP / Standards', 'weight': 12, 'patterns': ['3gpp', 'release 17', 'release 18', 'release 19', 'nr-ntn']},
]

# Fallback en caso de que la API falle o no haya clave
fallback = {
    'items': [
        {
            'title': 'AST SpaceMobile Makes History in 5G Broadband Cellular Connectivity from Space',
            'url': 'https://ast-science.com/2023/09/19/ast-spacemobile-makes-history-in-5g-broadband-cellular-connectivity-from-space/',
            'source': 'AST SpaceMobile Press',
            'publishedAt': '2023-09-19T00:00:00+00:00',
            'excerpt': 'First-ever 5G connection for voice and data between an everyday, unmodified smartphone and a satellite in space.',
            'score': 50,
            'tag': 'AST',
            'badge': 'Canonical Fallback'
        },
        {
            'title': 'T-Mobile Takes Coverage Above and Beyond With SpaceX',
            'url': 'https://www.t-mobile.com/news/un-carrier/t-mobile-takes-coverage-above-and-beyond-with-spacex',
            'source': 'T-Mobile Newsroom',
            'publishedAt': '2022-08-25T00:00:00+00:00',
            'excerpt': 'T-Mobile and SpaceX announce Coverage Above and Beyond using Starlink direct-to-cell connectivity.',
            'score': 45,
            'tag': 'Starlink',
            'badge': 'Canonical Fallback'
        }
    ],
    'count': 2,
    'lastUpdated': datetime.now(timezone.utc).isoformat(),
    'generator': 'fallback'
}


def clean_text(value: str) -> str:
    value = value or ''
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def fetch_query(query: str):
    params = {
        'q': query,
        'lang': 'en',
        'max': '10',
        'sortby': 'publishedAt',
        'apikey': API_KEY,
    }
    url = f"https://gnews.io/api/v4/search?{urlencode(params)}"
    req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def score_article(article):
    title = clean_text(article.get('title'))
    excerpt = clean_text(article.get('description'))
    source = clean_text((article.get('source') or {}).get('name', 'Unknown source'))
    text = f'{title} {excerpt}'.lower()

    score = 0
    tag = 'General'
    badge = 'MNO Relevant'
    best_weight = 0

    for rule in keyword_rules:
        hits = sum(1 for pattern in rule['patterns'] if pattern in text)
        if hits:
            score += hits * rule['weight']
            if rule['weight'] > best_weight:
                best_weight = rule['weight']
                tag = rule['tag']
                badge = rule['badge']

    for source_name, boost in source_boost.items():
        if source_name in source.lower():
            score += boost

    if re.search(r'partnership|trial|launch|commercial|beta|agreement|gateway|coverage|service|roaming', text):
        score += 10

    return {
        'title': title,
        'url': article.get('url'),
        'source': source,
        'publishedAt': article.get('publishedAt'),
        'excerpt': excerpt,
        'score': score,
        'tag': tag,
        'badge': badge,
    }


def main():
    os.makedirs('data', exist_ok=True)

    # Si no hay API key, escribir solo el fallback
    if not API_KEY:
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as fh:
            json.dump(fallback, fh, ensure_ascii=False, indent=2)
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    deduped = {}

    # Buscar noticias en cada query
    for query in queries:
        try:
            result = fetch_query(query)
        except Exception:
            continue

        for article in result.get('articles', []):
            published_at = article.get('publishedAt')
            if not published_at:
                continue
            try:
                dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            except Exception:
                continue
            if dt < cutoff:
                continue

            normalized = score_article(article)
            if not normalized['url']:
                continue

            key = normalized['url'].split('#')[0].lower()
            existing = deduped.get(key)
            if existing is None or normalized['score'] > existing['score']:
                deduped[key] = normalized

       # Ordenar por score y fecha
    ranked = sorted(
        deduped.values(),
        key=lambda x: (x['score'], x['publishedAt']),
        reverse=True
    )

    items = []
    ast_count = 0
    diversity_count = 0

    for item in ranked:
        if len(items) >= MAX_ITEMS:
            break

        if item.get('tag') == 'AST':
            if ast_count >= MAX_AST_ITEMS:
                continue
            ast_count += 1

        if item.get('tag') in DIVERSITY_TAGS:
            diversity_count += 1

        items.append(item)


    if diversity_count < MIN_DIVERSITY_ITEMS:
        existing_keys = {it['url'].split('#')[0].lower() for it in items if it.get('url')}
        for art in fallback['items']:
            key = art['url'].split('#')[0].lower()
        if key not in existing_keys:
            art_copy = dict(art)
            scored = score_article({
                'title': art_copy.get('title', ''),
                'description': art_copy.get('excerpt', ''),
                'url': art_copy.get('url', ''),
                'publishedAt': art_copy.get('publishedAt', ''),
                'source': {'name': art_copy.get('source', '')}
            })
            art_copy['tag'] = scored['tag']
            art_copy['badge'] = scored['badge']
            items.append(art_copy)
            existing_keys.add(key)
            if len(items) >= MAX_ITEMS:
                break
        
    # Rellenar con fallback si tenemos menos de MIN_ITEMS
    if len(items) < MIN_ITEMS:
        existing_keys = {it['url'].split('#')[0].lower() for it in items if it.get('url')}
        for art in fallback['items']:
            key = art['url'].split('#')[0].lower()
        if key not in existing_keys:
            art_copy = dict(art)
            scored = score_article({
                'title': art_copy.get('title', ''),
                'description': art_copy.get('excerpt', ''),
                'url': art_copy.get('url', ''),
                'publishedAt': art_copy.get('publishedAt', ''),
                'source': {'name': art_copy.get('source', '')}
            })
            art_copy['tag'] = scored['tag']
            art_copy['badge'] = scored['badge']
            items.append(art_copy)
            existing_keys.add(key)
            if len(items) >= MIN_ITEMS:
                break

    # Si aún así no hay nada, usar fallback completo
    if not items:
        payload = fallback
        payload['lastUpdated'] = datetime.now(timezone.utc).isoformat()
    else:
        payload = {
            'items': items,
            'count': len(items),
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
            'generator': 'github-actions-gnews+fallback' if len(items) < MAX_ITEMS else 'github-actions-gnews'
        }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
