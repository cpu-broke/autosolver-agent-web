import time, itertools
from collections import defaultdict, deque
BASE = 100.0
TIME_LIMIT = 7
SCENE_ADAPTIVE_MULTI_COURIER = True
MULTI_LOW_MAX_RIDERS = 8
MULTI_NORMAL_MAX_RIDERS = 4
MULTI_SCARCE_MAX_RIDERS = 2
MULTI_LOW_MIN_GAIN = 0.01
MULTI_NORMAL_MIN_GAIN = 0.5
MULTI_SCARCE_MIN_GAIN = 6.0
USE_SEQ_GROUP_COST = False
def _popcount(x):
    return bin(x).count('1')
def _parse(input_text):
    lines = input_text.strip().splitlines()
    start = 1 if lines and lines[0].startswith('task_id_list') else 0
    task_id = {}
    courier_id = {}
    cands = []
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 4:
            continue
        task_str = parts[0].strip()
        courier = parts[1].strip()
        try:
            score = float(parts[2])
            p = float(parts[3])
        except Exception:
            continue
        tasks = []
        mask = 0
        for t in task_str.split(','):
            t = t.strip()
            if not t:
                continue
            if t not in task_id:
                task_id[t] = len(task_id)
            tid = task_id[t]
            tasks.append(tid)
            mask |= 1 << tid
        if not tasks:
            continue
        if courier not in courier_id:
            courier_id[courier] = len(courier_id)
        k = len(tasks)
        cost = p * score + (1.0 - p) * BASE * k
        cands.append({'idx': len(cands), 'task_str': task_str, 'courier': courier, 'cidx': courier_id[courier], 'score': score, 'p': p, 'tasks': tuple(tasks), 'mask': mask, 'k': k, 'cost': cost, 'gain': BASE * k - cost})
    return (cands, len(task_id), len(courier_id))
def _compress(cands):
    best = {}
    for c in cands:
        key = (c['mask'], c['cidx'])
        old = best.get(key)
        if old is None or c['cost'] < old['cost']:
            best[key] = c
    out = []
    for c in best.values():
        nc = dict(c)
        nc['idx'] = len(out)
        out.append(nc)
    return out
def _stats(cands, task_count, courier_count):
    if not cands:
        return {'low': False, 'scarce': False, 'route_scarce': False, 'small': task_count <= 18}
    ps = sorted((c['p'] for c in cands))
    task_freq = [0] * max(1, task_count)
    courier_freq = [0] * max(1, courier_count)
    task_riders = [set() for _ in range(max(1, task_count))]
    task_eff = [set() for _ in range(max(1, task_count))]
    task_single_eff = [set() for _ in range(max(1, task_count))]
    eff_couriers = set()
    bundles = 0
    for c in cands:
        courier_freq[c['cidx']] += 1
        if c['k'] > 1:
            bundles += 1
        unit = c['cost'] / float(max(1, c['k']))
        gain = BASE * c['k'] - c['cost']
        eff = unit < 96.0 or gain > 4.0 or (c['p'] > 0.18 and c['score'] / float(c['k']) < 70.0)
        for t in c['tasks']:
            task_freq[t] += 1
            task_riders[t].add(c['cidx'])
            if eff:
                task_eff[t].add(c['cidx'])
                eff_couriers.add(c['cidx'])
            if c['k'] == 1 and eff:
                task_single_eff[t].add(c['cidx'])
    tf = sorted(task_freq)
    cf = sorted(courier_freq)
    avg_p = sum(ps) / float(len(ps))
    q10_p = ps[int((len(ps) - 1) * 0.1)]
    q25_p = ps[int((len(ps) - 1) * 0.25)]
    med_p = ps[int((len(ps) - 1) * 0.5)]
    low_scene = avg_p < 0.24 or (med_p < 0.22 and q25_p < 0.12) or (q10_p < 0.04 and q25_p < 0.15)
    avg_task_options = sum(task_freq) / float(max(1, task_count))
    avg_courier_options = sum(courier_freq) / float(max(1, courier_count))
    q25_task = tf[int((len(tf) - 1) * 0.25)]
    q25_courier = cf[int((len(cf) - 1) * 0.25)]
    bundle_ratio = bundles / float(max(1, len(cands)))
    eff_cnt = sorted((len(x) for x in task_eff))
    all_cnt = sorted((len(x) for x in task_riders))
    single_cnt = sorted((len(x) for x in task_single_eff))
    q10_eff = eff_cnt[int((len(eff_cnt) - 1) * 0.1)]
    q25_eff = eff_cnt[int((len(eff_cnt) - 1) * 0.25)]
    q25_all = all_cnt[int((len(all_cnt) - 1) * 0.25)]
    q25_single = single_cnt[int((len(single_cnt) - 1) * 0.25)]
    eff_courier_count = len(eff_couriers)
    scarce_votes = 0
    if float(task_count) / max(1, courier_count) > 1.1:
        scarce_votes += 1
    if avg_task_options < 120:
        scarce_votes += 1
    if q25_task < 60:
        scarce_votes += 1
    if avg_courier_options < 80:
        scarce_votes += 1
    if bundle_ratio > 0.55 and q25_courier < 45:
        scarce_votes += 1
    base_scarce = scarce_votes >= 2
    route_scarce = not low_scene and task_count >= 35 and (courier_count <= int(task_count * 1.55 + 0.5) or eff_courier_count <= int(task_count * 1.35 + 0.5) or q25_eff <= 18 or (q10_eff <= 10) or (q25_single <= 8) or (base_scarce and q25_all <= 32))
    return {'low': low_scene, 'scarce': base_scarce, 'route_scarce': route_scarce, 'small': task_count <= 18, 'avg_p': avg_p, 'bundle_ratio': bundle_ratio}
def _quantile_thresholds(values, bins):
    if not values or bins <= 1:
        return []
    vals = sorted(values)
    n = len(vals) - 1
    out = []
    last = None
    for b in range(1, bins):
        v = vals[int(n * b / float(bins))]
        if last is None or v != last:
            out.append(v)
            last = v
    return out
def _bucket(value, thresholds):
    lo = 0
    hi = len(thresholds)
    while lo < hi:
        mid = (lo + hi) // 2
        if value <= thresholds[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo
def _low_p_bucket(p):
    if p < 0.02:
        return 0
    if p < 0.04:
        return 1
    if p < 0.06:
        return 2
    if p < 0.08:
        return 3
    if p < 0.1:
        return 4
    if p < 0.15:
        return 5
    if p < 0.25:
        return 6
    return 7
def _hist_context(cands, task_count):
    score_th = _quantile_thresholds([c['score'] for c in cands], 16)
    p_th = _quantile_thresholds([c['p'] for c in cands], 8)
    task_deg = [0] * max(1, task_count)
    courier_count = 0
    for c in cands:
        if c['cidx'] + 1 > courier_count:
            courier_count = c['cidx'] + 1
        for t in c['tasks']:
            task_deg[t] += 1
    courier_deg = [0] * max(1, courier_count)
    for c in cands:
        courier_deg[c['cidx']] += 1
    return (score_th, p_th, task_deg, courier_deg)
def _rarity(c, task_deg, courier_deg):
    s = 0.0
    for t in c['tasks']:
        s += 1.0 / max(1.0, task_deg[t] ** 0.5)
    s += 0.2 / max(1.0, courier_deg[c['cidx']] ** 0.5)
    return s
def _cost_cov(sol, cands):
    cost = 0.0
    mask = 0
    for i in sol:
        c = cands[i]
        cost += c['cost']
        mask |= c['mask']
    return (cost, _popcount(mask))
def _clean(sol, cands):
    used_t = 0
    used_c = set()
    out = []
    if not sol:
        return out
    for i in sol:
        if not isinstance(i, int) or i < 0 or i >= len(cands):
            continue
        c = cands[i]
        if used_t & c['mask']:
            continue
        if c['cidx'] in used_c:
            continue
        out.append(i)
        used_t |= c['mask']
        used_c.add(c['cidx'])
    return out
def _key(sol, cands):
    clean = _clean(sol, cands)
    cost, cov = _cost_cov(clean, cands)
    return (cov, -cost, -len(clean))
def _complete_unique(cands, sol, task_count):
    sol = _clean(sol, cands)
    used_t = 0
    used_c = set()
    for i in sol:
        used_t |= cands[i]['mask']
        used_c.add(cands[i]['cidx'])
    if _popcount(used_t) >= task_count:
        return sol
    order = sorted(range(len(cands)), key=lambda i: (-_popcount(cands[i]['mask'] & ~used_t), cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['p'], -cands[i]['k']))
    for i in order:
        c = cands[i]
        if c['cidx'] in used_c:
            continue
        if c['mask'] & used_t:
            continue
        sol.append(i)
        used_t |= c['mask']
        used_c.add(c['cidx'])
        if _popcount(used_t) >= task_count:
            break
    return sol
def _safe_output(cands, sol):
    all_mask = 0
    for c in cands:
        all_mask |= c['mask']
    sol = _complete_unique(cands, sol, _popcount(all_mask))
    sol = sorted(sol, key=lambda i: (cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['p'], -cands[i]['k']))
    result = []
    used_t = 0
    used_c = set()
    for i in sol:
        c = cands[i]
        if used_t & c['mask']:
            continue
        if c['cidx'] in used_c:
            continue
        result.append((c['task_str'], [c['courier']]))
        used_t |= c['mask']
        used_c.add(c['cidx'])
    return result
def _group_expected_cost(cands, ids):
    if not ids:
        return 0.0
    if USE_SEQ_GROUP_COST:
        ordered = sorted(ids, key=lambda i: (cands[i]['score'], -cands[i]['p']))
        k = cands[ordered[0]]['k']
        fail = 1.0
        total = 0.0
        for i in ordered:
            c = cands[i]
            total += fail * c['p'] * c['score']
            fail *= 1.0 - c['p']
        return total + fail * BASE * k
    k = cands[ids[0]]['k']
    fail = 1.0
    psum = 0.0
    weighted_score = 0.0
    for i in ids:
        c = cands[i]
        fail *= 1.0 - c['p']
        psum += c['p']
        weighted_score += c['p'] * c['score']
    success_score = BASE * k if psum <= 1e-12 else weighted_score / psum
    return (1.0 - fail) * success_score + fail * BASE * k
def _group_fail_prob(cands, ids):
    fail = 1.0
    for i in ids:
        fail *= 1.0 - cands[i]['p']
    return fail
def _multi_params(st, task_count):
    if task_count <= 8:
        return (3, 1.5, task_count * 2, 140)
    if st.get('low'):
        return (MULTI_LOW_MAX_RIDERS, MULTI_LOW_MIN_GAIN, task_count * max(0, MULTI_LOW_MAX_RIDERS - 1), 260)
    if st.get('scarce'):
        return (MULTI_SCARCE_MAX_RIDERS, MULTI_SCARCE_MIN_GAIN, max(3, task_count // 3), 80)
    return (MULTI_NORMAL_MAX_RIDERS, MULTI_NORMAL_MIN_GAIN, task_count * 2, 140)
def _mask_multi_model(cands, st, task_count):
    max_riders, _min_gain, _max_extra, scan_cap = _multi_params(st, task_count)
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        by_mask[c['mask']].append(i)
    model = {}
    def make_group(arr):
        group = []
        used = set()
        checked = 0
        for i in arr:
            checked += 1
            c = cands[i]
            if c['cidx'] in used:
                continue
            if group:
                old = _group_expected_cost(cands, group)
                new = _group_expected_cost(cands, group + [i])
                if old - new <= -1e-09:
                    if checked >= scan_cap:
                        break
                    continue
            group.append(i)
            used.add(c['cidx'])
            if len(group) >= max_riders or checked >= scan_cap:
                break
        return tuple(group)
    for mask, arr in by_mask.items():
        orders = [sorted(arr, key=lambda i: (-(cands[i]['p'] * (BASE * cands[i]['k'] - cands[i]['score'])), cands[i]['score'], -cands[i]['p'])), sorted(arr, key=lambda i: (cands[i]['score'], -cands[i]['p'], cands[i]['cost'])), sorted(arr, key=lambda i: (-cands[i]['p'], cands[i]['score'], cands[i]['cost'])), sorted(arr, key=lambda i: (cands[i]['cost'], cands[i]['score'], -cands[i]['p'])), sorted(arr, key=lambda i: (cands[i]['score'] / max(cands[i]['p'], 0.01), cands[i]['score']))]
        variants = {}
        for order in orders:
            group = make_group(order)
            if group:
                variants[group] = (_group_expected_cost(cands, group), group, _group_fail_prob(cands, group))
        if variants:
            vals = list(variants.values())
            vals.sort(key=lambda x: (x[0], x[2], -len(x[1])))
            model[mask] = vals[:6]
    return model
def _safe_output_multi(cands, sol, task_count, st, deadline):
    if not SCENE_ADAPTIVE_MULTI_COURIER:
        return _safe_output(cands, sol)
    base = _complete_unique(cands, sol, task_count)
    base = sorted(base, key=lambda i: (cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['p'], -cands[i]['k']))
    groups = []
    used_t = 0
    used_c = set()
    for i in base:
        c = cands[i]
        if used_t & c['mask']:
            continue
        if c['cidx'] in used_c:
            continue
        groups.append([i])
        used_t |= c['mask']
        used_c.add(c['cidx'])
    if _popcount(used_t) < task_count:
        return _safe_output(cands, sol)
    max_riders, min_gain, max_extra, scan_cap = _multi_params(st, task_count)
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        by_mask[c['mask']].append(i)
    for m in by_mask:
        by_mask[m].sort(key=lambda i: (-(cands[i]['p'] * (BASE * cands[i]['k'] - cands[i]['score'])), cands[i]['score'], -cands[i]['p'], cands[i]['cost']))
    cur_cost = [_group_expected_cost(cands, g) for g in groups]
    cur_fail = [_group_fail_prob(cands, g) for g in groups]
    extra = 0
    while extra < max_extra and time.time() < deadline:
        best_score = min_gain
        best_gain = 0.0
        best_g = None
        best_i = None
        for gi, group in enumerate(groups):
            if len(group) >= max_riders:
                continue
            mask = cands[group[0]]['mask']
            checked = 0
            for i in by_mask.get(mask, []):
                c = cands[i]
                if c['cidx'] in used_c:
                    continue
                new_cost = _group_expected_cost(cands, group + [i])
                gain = cur_cost[gi] - new_cost
                if gain <= min_gain:
                    checked += 1
                    if checked >= scan_cap:
                        break
                    continue
                if st.get('low'):
                    score = gain * (1.0 + cur_fail[gi] * cands[group[0]]['k'])
                elif st.get('scarce'):
                    score = gain
                else:
                    score = gain
                if score > best_score:
                    best_score = score
                    best_gain = gain
                    best_g = gi
                    best_i = i
                checked += 1
                if checked >= scan_cap:
                    break
        if best_i is None:
            break
        groups[best_g].append(best_i)
        groups[best_g].sort(key=lambda i: (cands[i]['score'], -cands[i]['p']))
        used_c.add(cands[best_i]['cidx'])
        cur_cost[best_g] = _group_expected_cost(cands, groups[best_g])
        cur_fail[best_g] = _group_fail_prob(cands, groups[best_g])
        extra += 1
    result = []
    out_used_t = 0
    for group in groups:
        first = cands[group[0]]
        if out_used_t & first['mask']:
            continue
        couriers = []
        seen = set()
        for i in group:
            cid = cands[i]['courier']
            if cid in seen:
                continue
            seen.add(cid)
            couriers.append(cid)
        if couriers:
            result.append((first['task_str'], couriers))
            out_used_t |= first['mask']
    return result
def _output_expected_cost(cands, output):
    by_pair = {}
    for i, c in enumerate(cands):
        by_pair[c['task_str'], c['courier']] = i
    used_tasks = 0
    used_couriers = set()
    total = 0.0
    cov = 0
    pairs = 0
    for task_str, couriers in output:
        group = []
        mask = None
        for courier in couriers:
            i = by_pair.get((task_str, courier))
            if i is None:
                continue
            c = cands[i]
            if mask is None:
                mask = c['mask']
            elif mask != c['mask']:
                continue
            if c['cidx'] in used_couriers:
                continue
            group.append(i)
        if not group:
            continue
        first = cands[group[0]]
        if used_tasks & first['mask']:
            continue
        for i in group:
            used_couriers.add(cands[i]['cidx'])
            pairs += 1
        total += _group_expected_cost(cands, group)
        used_tasks |= first['mask']
    cov = _popcount(used_tasks)
    return (total, cov, pairs)
def _choose_best_multi_output(cands, candidates, task_count, st, deadline, output_candidates=None):
    if task_count <= 8:
        direct_best = None
        direct_key = None
        for _name, out in output_candidates or []:
            if time.time() >= deadline:
                break
            cost, cov, pairs = _output_expected_cost(cands, out)
            key = (cov, -cost, pairs)
            if direct_key is None or key > direct_key:
                direct_key = key
                direct_best = out
        ranked = []
        seen = set()
        for name, sol in candidates:
            clean = _clean(sol, cands)
            if not clean:
                continue
            sig = tuple(sorted(((cands[i]['mask'], cands[i]['cidx']) for i in clean)))
            if sig in seen:
                continue
            seen.add(sig)
            ranked.append((_key(clean, cands), name, clean))
        ranked.sort(reverse=True)
        regular_best = None
        regular_key = None
        max_eval = 10 if st.get('low') else 8
        deep_seconds = 0.46 if st.get('low') else 0.7
        for _k, _name, sol in ranked[:max_eval]:
            if time.time() >= deadline:
                break
            out = _safe_output_multi(cands, sol, task_count, st, min(deadline, time.time() + deep_seconds))
            cost, cov, pairs = _output_expected_cost(cands, out)
            key = (cov, -cost, pairs)
            if regular_key is None or key > regular_key:
                regular_key = key
                regular_best = out
        if direct_best is None:
            return regular_best
        if regular_best is None:
            return direct_best
        return direct_best if direct_key > regular_key else regular_best
    best_out = None
    best_key = None
    per_seconds = 0.24 if st.get('low') or st.get('scarce') else 0.20
    for _name, sol in candidates:
        if time.time() >= deadline:
            break
        per_deadline = min(deadline, time.time() + per_seconds)
        out = _safe_output_multi(cands, sol, task_count, st, per_deadline)
        cost, cov, pairs = _output_expected_cost(cands, out)
        key = (cov, -cost, pairs)
        if best_key is None or key > best_key:
            best_key = key
            best_out = out
    for _name, out in output_candidates or []:
        if time.time() >= deadline:
            break
        cost, cov, pairs = _output_expected_cost(cands, out)
        key = (cov, -cost, pairs)
        if best_key is None or key > best_key:
            best_key = key
            best_out = out
    return best_out
def _output_to_groups(cands, output):
    by_pair = {}
    for i, c in enumerate(cands):
        by_pair[c['task_str'], c['courier']] = i
    groups = []
    used_t = 0
    used_c = set()
    for task_str, couriers in output:
        group = []
        mask = None
        for courier in couriers:
            i = by_pair.get((task_str, courier))
            if i is None:
                continue
            c = cands[i]
            if mask is None:
                mask = c['mask']
            elif c['mask'] != mask:
                continue
            if c['cidx'] in used_c:
                continue
            group.append(i)
        if not group:
            continue
        m = cands[group[0]]['mask']
        if used_t & m:
            continue
        groups.append(group)
        used_t |= m
        for i in group:
            used_c.add(cands[i]['cidx'])
    return groups
def _groups_to_output(cands, groups):
    result = []
    used_t = 0
    used_c = set()
    for group in groups:
        if not group:
            continue
        first = cands[group[0]]
        if used_t & first['mask']:
            continue
        couriers = []
        ok = True
        seen = set()
        for i in group:
            c = cands[i]
            if c['mask'] != first['mask'] or c['cidx'] in used_c:
                ok = False
                break
            if c['courier'] in seen:
                continue
            seen.add(c['courier'])
            couriers.append(c['courier'])
        if ok and couriers:
            result.append((first['task_str'], couriers))
            used_t |= first['mask']
            for i in group:
                used_c.add(cands[i]['cidx'])
    return result
def _reassign_fixed_skeleton(cands, output, task_count, st, deadline):
    if st.get('low') or st.get('scarce') or task_count <= 8:
        return output
    groups = _output_to_groups(cands, output)
    if not groups:
        return output
    used_mask = 0
    used_c = set()
    for g in groups:
        used_mask |= cands[g[0]]['mask']
        for i in g:
            used_c.add(cands[i]['cidx'])
    if _popcount(used_mask) != task_count:
        return output
    by_mask_cidx = {}
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        key = (c['mask'], c['cidx'])
        old = by_mask_cidx.get(key)
        if old is None or c['score'] < cands[old]['score']:
            by_mask_cidx[key] = i
    for i in by_mask_cidx.values():
        by_mask[cands[i]['mask']].append(i)
    for mask in by_mask:
        by_mask[mask].sort(key=lambda i: (cands[i]['score'], -cands[i]['p'], cands[i]['cost']))
    costs = [_group_expected_cost(cands, g) for g in groups]
    improved = True
    loops = 0
    while improved and loops < 32 and (time.time() < deadline):
        improved = False
        loops += 1
        for gi, group in enumerate(groups):
            if time.time() >= deadline:
                break
            mask = cands[group[0]]['mask']
            local_cidx = set((cands[i]['cidx'] for i in group))
            for cand in by_mask.get(mask, [])[:90]:
                cc = cands[cand]['cidx']
                if cc in used_c or cc in local_cidx:
                    continue
                for pos, old in enumerate(group):
                    old_cost = costs[gi]
                    ng = group[:]
                    ng[pos] = cand
                    new_cost = _group_expected_cost(cands, ng)
                    if new_cost + 1e-09 < old_cost:
                        used_c.remove(cands[old]['cidx'])
                        used_c.add(cc)
                        groups[gi] = ng
                        costs[gi] = new_cost
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
        if improved:
            continue
        for gi in range(len(groups)):
            if time.time() >= deadline:
                break
            if len(groups[gi]) <= 1:
                continue
            for gj in range(len(groups)):
                if gi == gj or len(groups[gj]) >= MULTI_NORMAL_MAX_RIDERS:
                    continue
                mask_j = cands[groups[gj][0]]['mask']
                for pos, old in enumerate(groups[gi]):
                    moved = by_mask_cidx.get((mask_j, cands[old]['cidx']))
                    if moved is None:
                        continue
                    ng_i = groups[gi][:pos] + groups[gi][pos + 1:]
                    ng_j = groups[gj] + [moved]
                    new_total = _group_expected_cost(cands, ng_i) + _group_expected_cost(cands, ng_j)
                    old_total = costs[gi] + costs[gj]
                    if new_total + 1e-09 < old_total:
                        groups[gi] = ng_i
                        groups[gj] = ng_j
                        costs[gi] = _group_expected_cost(cands, ng_i)
                        costs[gj] = _group_expected_cost(cands, ng_j)
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
        if improved:
            continue
        for gi in range(len(groups)):
            if time.time() >= deadline:
                break
            mask_i = cands[groups[gi][0]]['mask']
            for gj in range(gi + 1, len(groups)):
                mask_j = cands[groups[gj][0]]['mask']
                old_total = costs[gi] + costs[gj]
                for pi, old_i in enumerate(groups[gi]):
                    ni_for_j = by_mask_cidx.get((mask_j, cands[old_i]['cidx']))
                    if ni_for_j is None:
                        continue
                    for pj, old_j in enumerate(groups[gj]):
                        nj_for_i = by_mask_cidx.get((mask_i, cands[old_j]['cidx']))
                        if nj_for_i is None:
                            continue
                        ng_i = groups[gi][:]
                        ng_j = groups[gj][:]
                        ng_i[pi] = nj_for_i
                        ng_j[pj] = ni_for_j
                        new_total = _group_expected_cost(cands, ng_i) + _group_expected_cost(cands, ng_j)
                        if new_total + 1e-09 < old_total:
                            groups[gi] = ng_i
                            groups[gj] = ng_j
                            costs[gi] = _group_expected_cost(cands, ng_i)
                            costs[gj] = _group_expected_cost(cands, ng_j)
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    new_out = _groups_to_output(cands, groups)
    old_cost, old_cov, _old_pairs = _output_expected_cost(cands, output)
    new_cost, new_cov, _new_pairs = _output_expected_cost(cands, new_out)
    if new_cov == task_count and new_cost + 1e-09 < old_cost:
        return new_out
    return output
def _small_multi_group_exact_output(cands, task_count, st, deadline):
    if task_count > 8 or time.time() >= deadline:
        return []
    max_riders = 7
    keep_per_mask = 12
    topn = 36
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        by_mask[c['mask']].append(i)
    rows = []
    seen_row = set()
    def add_group(mask, group):
        if not group:
            return
        used_c = set()
        g = []
        for i in group:
            cidx = cands[i]['cidx']
            if cidx in used_c:
                continue
            used_c.add(cidx)
            g.append(i)
            if len(g) >= max_riders:
                break
        if not g:
            return
        key = (mask, tuple(sorted((cands[i]['cidx'] for i in g))))
        if key in seen_row:
            return
        seen_row.add(key)
        cmask = 0
        for i in g:
            cmask |= 1 << cands[i]['cidx']
        rows.append({'mask': mask, 'cmask': cmask, 'group': tuple(g), 'cost': _group_expected_cost(cands, g), 'fail': _group_fail_prob(cands, g), 'riders': len(g)})
    def prefix_variants(order, mask):
        cur = []
        used = set()
        for i in order:
            cidx = cands[i]['cidx']
            if cidx in used:
                continue
            cur.append(i)
            used.add(cidx)
            add_group(mask, cur[:])
            if len(cur) >= max_riders:
                break
    def marginal_variants(order, mask):
        if not order:
            return
        for seed in order[:min(4, len(order))]:
            group = [seed]
            used = set([cands[seed]['cidx']])
            add_group(mask, group)
            while len(group) < max_riders:
                before = _group_expected_cost(cands, group)
                best_i = None
                best_gain = 1e-09
                for i in order[:topn]:
                    if cands[i]['cidx'] in used:
                        continue
                    gain = before - _group_expected_cost(cands, group + [i])
                    if gain > best_gain:
                        best_gain = gain
                        best_i = i
                if best_i is None:
                    break
                group.append(best_i)
                used.add(cands[best_i]['cidx'])
                add_group(mask, group[:])
    for mask, arr in by_mask.items():
        if time.time() >= deadline:
            break
        orders = [sorted(arr, key=lambda i: (cands[i]['score'], -cands[i]['p'], cands[i]['cost']))[:topn], sorted(arr, key=lambda i: (-cands[i]['p'], cands[i]['score'], cands[i]['cost']))[:topn], sorted(arr, key=lambda i: (-(cands[i]['p'] * (BASE * cands[i]['k'] - cands[i]['score'])), cands[i]['score'], -cands[i]['p']))[:topn], sorted(arr, key=lambda i: (cands[i]['cost'], cands[i]['score'], -cands[i]['p']))[:topn]]
        start_len = len(rows)
        for order in orders:
            prefix_variants(order, mask)
            marginal_variants(order, mask)
        local = rows[start_len:]
        if len(local) > keep_per_mask:
            local.sort(key=lambda r: (r['cost'], r['fail'], -r['riders']))
            keep = set((id(r) for r in local[:keep_per_mask]))
            rows[:] = rows[:start_len] + [r for r in local if id(r) in keep]
    if not rows:
        return []
    by_task = [[] for _ in range(task_count)]
    for rid, r in enumerate(rows):
        m = r['mask']
        while m:
            b = m & -m
            t = b.bit_length() - 1
            by_task[t].append(rid)
            m -= b
    for t in range(task_count):
        if not by_task[t]:
            return []
        by_task[t].sort(key=lambda rid: (rows[rid]['cost'] / max(1, _popcount(rows[rid]['mask'])), rows[rid]['cost'], rows[rid]['fail'], -rows[rid]['riders']))
    all_mask = (1 << task_count) - 1
    best_cost = [10 ** 100]
    best_sel = [()]
    calls = [0]
    max_calls = 900000
    min_unit = [10 ** 50] * task_count
    for r in rows:
        u = r['cost'] / max(1, _popcount(r['mask']))
        m = r['mask']
        while m:
            b = m & -m
            t = b.bit_length() - 1
            if u < min_unit[t]:
                min_unit[t] = u
            m -= b
    lb_cache = {}
    def lower_bound(mask):
        rem = all_mask & ~mask
        got = lb_cache.get(rem)
        if got is not None:
            return got
        s = 0.0
        m = rem
        while m:
            b = m & -m
            t = b.bit_length() - 1
            s += min_unit[t]
            m -= b
        s *= 0.45
        lb_cache[rem] = s
        return s
    def choose_task(mask, cmask):
        rem = all_mask & ~mask
        best_opts = None
        best_cnt = 10 ** 9
        m = rem
        while m:
            b = m & -m
            t = b.bit_length() - 1
            m -= b
            opts = []
            for rid in by_task[t]:
                r = rows[rid]
                if r['mask'] & mask:
                    continue
                if r['cmask'] & cmask:
                    continue
                opts.append(rid)
            if len(opts) < best_cnt:
                best_cnt = len(opts)
                best_opts = opts
                if best_cnt <= 1:
                    break
        return best_opts
    def dfs(mask, cmask, cost, path):
        calls[0] += 1
        if calls[0] > max_calls:
            return
        if calls[0] % 512 == 0 and time.time() >= deadline:
            return
        if mask == all_mask:
            if cost < best_cost[0] - 1e-09:
                best_cost[0] = cost
                best_sel[0] = tuple(path)
            return
        if cost + lower_bound(mask) >= best_cost[0] - 1e-09:
            return
        opts = choose_task(mask, cmask)
        if not opts:
            return
        for rid in opts:
            r = rows[rid]
            if r['mask'] & mask:
                continue
            if r['cmask'] & cmask:
                continue
            nc = cost + r['cost']
            if nc >= best_cost[0] - 1e-09:
                continue
            path.append(rid)
            dfs(mask | r['mask'], cmask | r['cmask'], nc, path)
            path.pop()
            if time.time() >= deadline:
                return
    dfs(0, 0, 0.0, [])
    if not best_sel[0]:
        return []
    result = []
    used_t = 0
    used_c = set()
    for rid in best_sel[0]:
        r = rows[rid]
        if used_t & r['mask']:
            continue
        couriers = []
        ok = True
        for i in r['group']:
            c = cands[i]
            if c['cidx'] in used_c:
                ok = False
                break
            couriers.append(c['courier'])
        if not ok or not couriers:
            continue
        first = cands[r['group'][0]]
        result.append((first['task_str'], couriers))
        used_t |= r['mask']
        for i in r['group']:
            used_c.add(cands[i]['cidx'])
    if _popcount(used_t) != task_count:
        return []
    return result
def _exact_small_dp_unique(cands, task_count, deadline, incumbent=None):
    if task_count > 16 or time.time() >= deadline:
        return incumbent or []
    all_mask = (1 << task_count) - 1
    best_by_key = {}
    for i, c in enumerate(cands):
        key = (c['mask'], c['cidx'])
        old = best_by_key.get(key)
        if old is None or c['cost'] < cands[old]['cost']:
            best_by_key[key] = i
    ids = list(best_by_key.values())
    by_task = [[] for _ in range(task_count)]
    for i in ids:
        for t in cands[i]['tasks']:
            by_task[t].append(i)
    for t in range(task_count):
        if not by_task[t]:
            return incumbent or []
        by_task[t].sort(key=lambda i: (cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['k'], -cands[i]['p']))
        if task_count > 8:
            by_task[t] = by_task[t][:260]
    inc = _clean(incumbent or [], cands)
    best_sol = [tuple(inc)]
    best_cost = [10 ** 100]
    cst, cov = _cost_cov(inc, cands)
    if cov == task_count:
        best_cost[0] = cst
    memo = {}
    calls = [0]
    def choose_task(mask, cmask):
        rem = all_mask & ~mask
        best_t = -1
        best_opts = None
        best_cnt = 10 ** 9
        m = rem
        while m:
            b = m & -m
            t = b.bit_length() - 1
            m -= b
            opts = []
            for i in by_task[t]:
                c = cands[i]
                if c['mask'] & mask:
                    continue
                if cmask & 1 << c['cidx']:
                    continue
                opts.append(i)
                if task_count > 8 and len(opts) >= 48:
                    break
            if len(opts) < best_cnt:
                best_cnt = len(opts)
                best_t = t
                best_opts = opts
                if best_cnt <= 1:
                    break
        return (best_t, best_opts)
    def dfs(mask, cmask, cost, path):
        calls[0] += 1
        max_calls = 900000 if task_count <= 8 else 260000
        if calls[0] > max_calls:
            return
        if calls[0] % 512 == 0 and time.time() >= deadline:
            return
        if cost >= best_cost[0] - 1e-09:
            return
        old = memo.get((mask, cmask))
        if old is not None and old <= cost + 1e-09:
            return
        memo[mask, cmask] = cost
        if mask == all_mask:
            best_cost[0] = cost
            best_sol[0] = tuple(path)
            return
        _t, opts = choose_task(mask, cmask)
        if not opts:
            return
        for i in opts:
            c = cands[i]
            bit = 1 << c['cidx']
            if c['mask'] & mask or cmask & bit:
                continue
            path.append(i)
            dfs(mask | c['mask'], cmask | bit, cost + c['cost'], path)
            path.pop()
            if time.time() >= deadline:
                return
    dfs(0, 0, 0.0, [])
    return list(best_sol[0]) if best_sol[0] else incumbent or []
def _mcmf_single(cands, task_count, courier_count):
    best_edge = {}
    for i, c in enumerate(cands):
        if c['k'] != 1:
            continue
        t = c['tasks'][0]
        key = (t, c['cidx'])
        old = best_edge.get(key)
        if old is None or c['cost'] < cands[old]['cost']:
            best_edge[key] = i
    n = 1 + task_count + courier_count + 1
    src = 0
    tb = 1
    cb = tb + task_count
    sink = n - 1
    g = [[] for _ in range(n)]
    def add(u, v, cap, cost, idx):
        g[u].append([v, cap, cost, len(g[v]), idx])
        g[v].append([u, 0, -cost, len(g[u]) - 1, -1])
    for t in range(task_count):
        add(src, tb + t, 1, 0, -1)
    scale = 1000000
    for (t, cidx), idx in best_edge.items():
        add(tb + t, cb + cidx, 1, int(round(cands[idx]['cost'] * scale)), idx)
    for cidx in range(courier_count):
        add(cb + cidx, sink, 1, 0, -1)
    flow = 0
    INF = 10 ** 30
    while flow < task_count:
        dist = [INF] * n
        inq = [False] * n
        pv = [-1] * n
        pe = [-1] * n
        dist[src] = 0
        q = deque([src])
        inq[src] = True
        while q:
            u = q.popleft()
            inq[u] = False
            for ei, e in enumerate(g[u]):
                if e[1] <= 0:
                    continue
                v = e[0]
                nd = dist[u] + e[2]
                if nd < dist[v]:
                    dist[v] = nd
                    pv[v] = u
                    pe[v] = ei
                    if not inq[v]:
                        inq[v] = True
                        q.append(v)
        if dist[sink] >= INF:
            break
        v = sink
        while v != src:
            u = pv[v]
            ei = pe[v]
            e = g[u][ei]
            e[1] -= 1
            g[v][e[3]][1] += 1
            v = u
        flow += 1
    if flow != task_count:
        return []
    sel = []
    for t in range(task_count):
        u = tb + t
        for e in g[u]:
            if e[4] >= 0 and e[1] == 0:
                sel.append(e[4])
                break
    return sel
def _greedy_unique(cands, task_count, order):
    used_t = 0
    used_c = set()
    sol = []
    for i in order:
        c = cands[i]
        if used_t & c['mask']:
            continue
        if c['cidx'] in used_c:
            continue
        sol.append(i)
        used_t |= c['mask']
        used_c.add(c['cidx'])
        if _popcount(used_t) >= task_count:
            break
    return sol
def _greedy_candidates(cands, task_count):
    ids = list(range(len(cands)))
    score_th, p_th, task_deg, courier_deg = _hist_context(cands, task_count)
    def sb(i):
        return _bucket(cands[i]['score'], score_th)
    def pb(i):
        return _bucket(cands[i]['p'], p_th)
    def lp(i):
        return _low_p_bucket(cands[i]['p'])
    def rare(i):
        return _rarity(cands[i], task_deg, courier_deg)
    def benefit(i):
        c = cands[i]
        return c['p'] * (BASE * c['k'] - c['score'])
    orders = [sorted(ids, key=lambda i: (cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['p'], -cands[i]['k'])), sorted(ids, key=lambda i: (-cands[i]['k'], cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['p'])), sorted(ids, key=lambda i: (cands[i]['score'] / cands[i]['k'], cands[i]['cost'] / cands[i]['k'], -cands[i]['p'])), sorted(ids, key=lambda i: (-cands[i]['gain'], cands[i]['cost'], -cands[i]['k'])), sorted(ids, key=lambda i: (-benefit(i), -cands[i]['k'], cands[i]['score'] / cands[i]['k'], -cands[i]['p'])), sorted(ids, key=lambda i: (-cands[i]['k'], sb(i), -pb(i), rare(i), cands[i]['score'] / cands[i]['k'], cands[i]['cost'] / cands[i]['k'])), sorted(ids, key=lambda i: (-cands[i]['k'], sb(i), -lp(i), rare(i), -benefit(i), cands[i]['cost'] / cands[i]['k'])), sorted(ids, key=lambda i: (rare(i), cands[i]['cost'] / cands[i]['k'], -cands[i]['p'], -cands[i]['k']))]
    return [_greedy_unique(cands, task_count, o) for o in orders]
def _beam_cover_unique(cands, task_count, deadline, limit):
    if time.time() >= deadline:
        return []
    all_mask = (1 << task_count) - 1
    score_th, p_th, task_deg, courier_deg = _hist_context(cands, task_count)
    def sb(i):
        return _bucket(cands[i]['score'], score_th)
    def benefit(i):
        c = cands[i]
        return c['p'] * (BASE * c['k'] - c['score'])
    by_task = [[] for _ in range(task_count)]
    for i, c in enumerate(cands):
        for t in c['tasks']:
            by_task[t].append(i)
    for t in range(task_count):
        if not by_task[t]:
            return []
        by_task[t].sort(key=lambda i: (-cands[i]['k'], -benefit(i), sb(i), _rarity(cands[i], task_deg, courier_deg), cands[i]['cost'] / cands[i]['k'], -cands[i]['p']))
        by_task[t] = by_task[t][:90]
    task_order = list(range(task_count))
    task_order.sort(key=lambda t: len(by_task[t]))
    states = [(0, 0, 0.0, ())]
    for t in task_order:
        if time.time() >= deadline:
            break
        new_states = []
        for mask, cmask, cost, sel in states:
            if mask & 1 << t:
                new_states.append((mask, cmask, cost, sel))
                continue
            for i in by_task[t]:
                c = cands[i]
                cb = 1 << c['cidx']
                if mask & c['mask']:
                    continue
                if cmask & cb:
                    continue
                new_states.append((mask | c['mask'], cmask | cb, cost + c['cost'], sel + (i,)))
        if not new_states:
            return []
        best_by_mask = {}
        for item in new_states:
            mask, cmask, cost, sel = item
            key = (mask, cmask)
            old = best_by_mask.get(key)
            if old is None or cost < old[2]:
                best_by_mask[key] = item
        states = list(best_by_mask.values())
        if len(states) > limit:
            states.sort(key=lambda x: (-_popcount(x[0]), x[2] + BASE * (task_count - _popcount(x[0])), len(x[3])))
            states = states[:limit]
    best = ()
    best_key = None
    for mask, cmask, cost, sel in states:
        key = (_popcount(mask), -cost, -len(sel))
        if best_key is None or key > best_key:
            best_key = key
            best = sel
        if mask == all_mask:
            key = (task_count, -cost, -len(sel))
            if best_key is None or key > best_key:
                best_key = key
                best = sel
    return list(best)
def _multi_potential_candidate(cands, task_count, st):
    if st.get('low'):
        max_riders = MULTI_LOW_MAX_RIDERS
    elif st.get('scarce'):
        max_riders = MULTI_SCARCE_MAX_RIDERS
    else:
        max_riders = MULTI_NORMAL_MAX_RIDERS
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        by_mask[c['mask']].append(i)
    potential = {}
    preferred = {}
    model = _mask_multi_model(cands, st, task_count)
    for mask, variants in model.items():
        cost, group, _fail = variants[0]
        if group:
            potential[mask] = cost / float(cands[group[0]]['k'])
            preferred[mask] = group[0]
    ids = list(range(len(cands)))
    order = sorted(ids, key=lambda i: (potential.get(cands[i]['mask'], cands[i]['cost'] / cands[i]['k']), 0 if preferred.get(cands[i]['mask']) == i else 1, -cands[i]['k'], cands[i]['cost'] / cands[i]['k'], -cands[i]['p']))
    return _greedy_unique(cands, task_count, order)
def _multi_model_beam_candidate(cands, task_count, st, deadline, limit):
    if time.time() >= deadline:
        return []
    model = _mask_multi_model(cands, st, task_count)
    if not model:
        return []
    rows = []
    for mask, variants in model.items():
        for cost, group, fail in variants:
            if not group:
                continue
            cmask = 0
            for i in group:
                cmask |= 1 << cands[i]['cidx']
            rows.append((mask, cost, group[0], cmask, fail, len(group)))
    by_task = [[] for _ in range(task_count)]
    for row in rows:
        mask = row[0]
        m = mask
        while m:
            b = m & -m
            t = b.bit_length() - 1
            by_task[t].append(row)
            m -= b
    for t in range(task_count):
        if not by_task[t]:
            return []
        by_task[t].sort(key=lambda r: (r[1] / max(1, _popcount(r[0])), -_popcount(r[0]), r[4], -r[5]))
        by_task[t] = by_task[t][:220]
    task_order = list(range(task_count))
    task_order.sort(key=lambda t: len(by_task[t]))
    states = [(0, 0, 0.0, ())]
    for t in task_order:
        if time.time() >= deadline:
            break
        new_states = []
        bit = 1 << t
        for mask, cmask, cost, sel in states:
            if mask & bit:
                new_states.append((mask, cmask, cost, sel))
                continue
            for rmask, rcost, rid, rcmask, _fail, _gsize in by_task[t]:
                if mask & rmask:
                    continue
                if cmask & rcmask:
                    continue
                new_states.append((mask | rmask, cmask | rcmask, cost + rcost, sel + (rid,)))
        if not new_states:
            return []
        best = {}
        for item in new_states:
            mask, cmask, cost, sel = item
            key = (mask, cmask)
            old = best.get(key)
            if old is None or cost < old[2]:
                best[key] = item
        states = list(best.values())
        if len(states) > limit:
            states.sort(key=lambda x: (-_popcount(x[0]), x[2] + BASE * (task_count - _popcount(x[0])), len(x[3])))
            states = states[:limit]
    best_sel = ()
    best_key = None
    for mask, cmask, cost, sel in states:
        key = (_popcount(mask), -cost, -len(sel))
        if best_key is None or key > best_key:
            best_key = key
            best_sel = sel
    return list(best_sel)
def _multi_model_beam_output(cands, task_count, st, deadline, limit):
    if time.time() >= deadline:
        return []
    model = _mask_multi_model(cands, st, task_count)
    if not model:
        return []
    rows = []
    for mask, variants in model.items():
        for cost, group, fail in variants:
            if not group:
                continue
            cmask = 0
            for i in group:
                cmask |= 1 << cands[i]['cidx']
            rows.append((mask, cost, group, cmask, fail, len(group)))
    by_task = [[] for _ in range(task_count)]
    for rid, row in enumerate(rows):
        mask = row[0]
        m = mask
        while m:
            b = m & -m
            t = b.bit_length() - 1
            by_task[t].append(rid)
            m -= b
    for t in range(task_count):
        if not by_task[t]:
            return []
        by_task[t].sort(key=lambda rid: (rows[rid][1] / max(1, _popcount(rows[rid][0])), -_popcount(rows[rid][0]), rows[rid][4], -rows[rid][5]))
        by_task[t] = by_task[t][:220]
    task_order = list(range(task_count))
    task_order.sort(key=lambda t: len(by_task[t]))
    states = [(0, 0, 0.0, ())]
    for t in task_order:
        if time.time() >= deadline:
            break
        bit = 1 << t
        new_states = []
        for mask, cmask, cost, sel in states:
            if mask & bit:
                new_states.append((mask, cmask, cost, sel))
                continue
            for rid in by_task[t]:
                rmask, rcost, _group, rcmask, _fail, _gsize = rows[rid]
                if mask & rmask:
                    continue
                if cmask & rcmask:
                    continue
                new_states.append((mask | rmask, cmask | rcmask, cost + rcost, sel + (rid,)))
        if not new_states:
            return []
        best = {}
        for item in new_states:
            mask, cmask, cost, sel = item
            key = (mask, cmask)
            old = best.get(key)
            if old is None or cost < old[2]:
                best[key] = item
        states = list(best.values())
        if len(states) > limit:
            states.sort(key=lambda x: (-_popcount(x[0]), x[2] + BASE * (task_count - _popcount(x[0])), len(x[3])))
            states = states[:limit]
    best_sel = ()
    best_key = None
    for mask, cmask, cost, sel in states:
        key = (_popcount(mask), -cost, -len(sel))
        if best_key is None or key > best_key:
            best_key = key
            best_sel = sel
    result = []
    used_t = 0
    used_c = set()
    for rid in best_sel:
        mask, _cost, group, _cmask, _fail, _gsize = rows[rid]
        if used_t & mask:
            continue
        couriers = []
        ok = True
        for i in group:
            c = cands[i]
            if c['cidx'] in used_c:
                ok = False
                break
            couriers.append(c['courier'])
        if not ok:
            continue
        first = cands[group[0]]
        result.append((first['task_str'], couriers))
        used_t |= mask
        for i in group:
            used_c.add(cands[i]['cidx'])
    return result
def _multi_bundle_first_candidate(cands, task_count, st):
    model = _mask_multi_model(cands, st, task_count)
    if not model:
        return []
    best_by_mask = {}
    for mask, variants in model.items():
        if variants:
            best_by_mask[mask] = variants[0][0]
    ids = list(range(len(cands)))
    order = sorted(ids, key=lambda i: (best_by_mask.get(cands[i]['mask'], cands[i]['cost']) / max(1, cands[i]['k']), -cands[i]['k'], best_by_mask.get(cands[i]['mask'], cands[i]['cost']), cands[i]['cost'] / cands[i]['k'], -cands[i]['p']))
    return _greedy_unique(cands, task_count, order)
def _exact_small_unique(cands, task_count, courier_count, deadline, incumbent=None):
    if task_count > 18 or time.time() >= deadline:
        return incumbent or []
    all_mask = (1 << task_count) - 1
    best = {}
    for i, c in enumerate(cands):
        key = (c['mask'], c['cidx'])
        old = best.get(key)
        if old is None or c['cost'] < cands[old]['cost']:
            best[key] = i
    ids = list(best.values())
    by_task = [[] for _ in range(task_count)]
    for i in ids:
        for t in cands[i]['tasks']:
            by_task[t].append(i)
    for t in range(task_count):
        if not by_task[t]:
            return incumbent or []
        by_task[t].sort(key=lambda i: (cands[i]['cost'] / cands[i]['k'], cands[i]['cost'], -cands[i]['k'], -cands[i]['p']))
        if task_count > 8:
            by_task[t] = by_task[t][:360]
    best_sol = [tuple(incumbent or [])]
    best_cost = [10 ** 100]
    if incumbent:
        cst, cov = _cost_cov(_clean(incumbent, cands), cands)
        if cov == task_count:
            best_cost[0] = cst
    if best_cost[0] >= 10 ** 90:
        s = _mcmf_single(cands, task_count, courier_count)
        if s:
            cst, cov = _cost_cov(s, cands)
            if cov == task_count:
                best_sol[0] = tuple(s)
                best_cost[0] = cst
    min_unit = [10 ** 50] * task_count
    for i in ids:
        c = cands[i]
        u = c['cost'] / c['k']
        for t in c['tasks']:
            if u < min_unit[t]:
                min_unit[t] = u
    lb_cache = {}
    def lb(mask):
        rem = all_mask & ~mask
        got = lb_cache.get(rem)
        if got is not None:
            return got
        s = 0.0
        m = rem
        while m:
            b = m & -m
            t = b.bit_length() - 1
            s += min_unit[t]
            m -= b
        s *= 0.5
        lb_cache[rem] = s
        return s
    calls = [0]
    def choose_task(mask, used_c):
        rem = all_mask & ~mask
        bt = -1
        bopts = None
        bcnt = 10 ** 9
        m = rem
        while m:
            b = m & -m
            t = b.bit_length() - 1
            m -= b
            opts = []
            for i in by_task[t]:
                c = cands[i]
                if c['mask'] & mask:
                    continue
                if c['cidx'] in used_c:
                    continue
                opts.append(i)
                if task_count > 8 and len(opts) >= 50:
                    break
            if len(opts) < bcnt:
                bcnt = len(opts)
                bt = t
                bopts = opts
                if bcnt <= 1:
                    break
        return (bt, bopts)
    def dfs(mask, used_c, cost, path):
        calls[0] += 1
        max_calls = 900000 if task_count <= 8 else 420000
        if calls[0] > max_calls:
            return
        if calls[0] % 512 == 0 and time.time() >= deadline:
            return
        if mask == all_mask:
            if cost < best_cost[0] - 1e-09:
                best_cost[0] = cost
                best_sol[0] = tuple(path)
            return
        if cost + lb(mask) >= best_cost[0] - 1e-09:
            return
        t, opts = choose_task(mask, used_c)
        if t < 0 or not opts:
            return
        for i in opts:
            c = cands[i]
            if c['mask'] & mask or c['cidx'] in used_c:
                continue
            nc = cost + c['cost']
            if nc >= best_cost[0] - 1e-09:
                continue
            used_c.add(c['cidx'])
            path.append(i)
            dfs(mask | c['mask'], used_c, nc, path)
            path.pop()
            used_c.remove(c['cidx'])
            if time.time() >= deadline:
                return
    dfs(0, set(), 0.0, [])
    return list(best_sol[0]) if best_sol[0] else incumbent or []
def _bundle_savings_unique(cands, base_sol, task_count, deadline):
    if not base_sol or time.time() >= deadline:
        return base_sol
    base = _clean(base_sol, cands)
    base_cost, base_cov = _cost_cov(base, cands)
    if base_cov != task_count:
        return base_sol
    row_by_task = {}
    baseline_courier_task = {}
    for i in base:
        c = cands[i]
        baseline_courier_task[c['cidx']] = c['tasks'][0] if c['k'] == 1 else -1
        for t in c['tasks']:
            row_by_task[t] = i
    bundles = []
    for i, c in enumerate(cands):
        if c['k'] <= 1:
            continue
        rem_rows = set()
        ok = True
        saved = 0.0
        for t in c['tasks']:
            r = row_by_task.get(t)
            if r is None:
                ok = False
                break
            rem_rows.add(r)
        if not ok:
            continue
        for r in rem_rows:
            saved += cands[r]['cost']
        saving = saved - c['cost']
        if saving <= 1e-09:
            continue
        conflict_task = baseline_courier_task.get(c['cidx'])
        if conflict_task is not None and conflict_task >= 0 and (not c['mask'] & 1 << conflict_task):
            continue
        bundles.append((saving, i, c['mask'], c['cidx']))
    bundles.sort(reverse=True)
    selected = []
    used_mask = 0
    used_c = set()
    for _saving, i, mask, cidx in bundles:
        if time.time() >= deadline:
            break
        if used_mask & mask:
            continue
        if cidx in used_c:
            continue
        selected.append(i)
        used_mask |= mask
        used_c.add(cidx)
    if not selected:
        return base_sol
    removed_tasks = 0
    selected_c = set()
    for i in selected:
        removed_tasks |= cands[i]['mask']
        selected_c.add(cands[i]['cidx'])
    cand = []
    used_c_final = set()
    used_t_final = 0
    for i in base:
        c = cands[i]
        if c['mask'] & removed_tasks:
            continue
        if c['cidx'] in selected_c:
            continue
        cand.append(i)
        used_c_final.add(c['cidx'])
        used_t_final |= c['mask']
    for i in selected:
        c = cands[i]
        if used_t_final & c['mask']:
            continue
        if c['cidx'] in used_c_final:
            continue
        cand.append(i)
        used_t_final |= c['mask']
        used_c_final.add(c['cidx'])
    if _popcount(used_t_final) < task_count:
        for t in range(task_count):
            if used_t_final & 1 << t:
                continue
            best = None
            for i, c in enumerate(cands):
                if c['k'] != 1 or c['tasks'][0] != t:
                    continue
                if c['cidx'] in used_c_final:
                    continue
                if best is None or c['cost'] < cands[best]['cost']:
                    best = i
            if best is not None:
                cand.append(best)
                used_t_final |= cands[best]['mask']
                used_c_final.add(cands[best]['cidx'])
    cand = _clean(cand, cands)
    cc, cv = _cost_cov(cand, cands)
    if (cv, -cc) > (base_cov, -base_cost):
        return cand
    return base_sol
def _row_first_candidate(cands, task_count):
    ids = list(range(len(cands)))
    score_th, p_th, task_deg, courier_deg = _hist_context(cands, task_count)
    def sb(i):
        return _bucket(cands[i]['score'], score_th)
    def pb(i):
        return _bucket(cands[i]['p'], p_th)
    def lp(i):
        return _low_p_bucket(cands[i]['p'])
    def rare(i):
        return _rarity(cands[i], task_deg, courier_deg)
    def benefit(i):
        c = cands[i]
        return c['p'] * (BASE * c['k'] - c['score'])
    order = sorted(ids, key=lambda i: (-cands[i]['k'], sb(i), -pb(i), -lp(i), rare(i), -benefit(i), cands[i]['score'] / cands[i]['k'], cands[i]['cost'] / cands[i]['k']))
    return _greedy_unique(cands, task_count, order)
def _valid_groups_full(cands, groups, task_count):
    used_t = 0
    used_c = set()
    for g in groups:
        if not g:
            return False
        mask = cands[g[0]]['mask']
        for i in g:
            c = cands[i]
            if c['mask'] != mask:
                return False
            if c['cidx'] in used_c:
                return False
            used_c.add(c['cidx'])
        if used_t & mask:
            return False
        used_t |= mask
    return _popcount(used_t) == task_count
def _mask_group_variants(cands, arr, banned_cidx, max_riders, keep):
    if not arr:
        return []
    orders = [sorted(arr, key=lambda i: (cands[i]['score'], -cands[i]['p'], cands[i]['cost'])), sorted(arr, key=lambda i: (-cands[i]['p'], cands[i]['score'], cands[i]['cost'])), sorted(arr, key=lambda i: (-(cands[i]['p'] * (BASE * cands[i]['k'] - cands[i]['score'])), cands[i]['score'], -cands[i]['p'])), sorted(arr, key=lambda i: (cands[i]['cost'], cands[i]['score'], -cands[i]['p']))]
    out = {}
    def add(g):
        if not g:
            return
        used = set()
        gg = []
        for i in g:
            ci = cands[i]['cidx']
            if ci in banned_cidx or ci in used:
                continue
            used.add(ci)
            gg.append(i)
            if len(gg) >= max_riders:
                break
        if not gg:
            return
        key = tuple(sorted((cands[i]['cidx'] for i in gg)))
        cost = _group_expected_cost(cands, gg)
        old = out.get(key)
        if old is None or cost < old[0]:
            out[key] = (cost, tuple(gg))
    for order in orders:
        cur = []
        used = set()
        for i in order[:48]:
            ci = cands[i]['cidx']
            if ci in banned_cidx or ci in used:
                continue
            cur.append(i)
            used.add(ci)
            add(cur)
            if len(cur) >= max_riders:
                break
        for seed in order[:3]:
            if cands[seed]['cidx'] in banned_cidx:
                continue
            g = [seed]
            used = set([cands[seed]['cidx']])
            add(g)
            while len(g) < max_riders:
                before = _group_expected_cost(cands, g)
                bi = None
                bg = 1e-09
                for i in order[:48]:
                    ci = cands[i]['cidx']
                    if ci in banned_cidx or ci in used:
                        continue
                    gain = before - _group_expected_cost(cands, g + [i])
                    if gain > bg:
                        bg = gain
                        bi = i
                if bi is None:
                    break
                g.append(bi)
                used.add(cands[bi]['cidx'])
                add(g)
    vals = list(out.values())
    vals.sort(key=lambda x: (x[0], _group_fail_prob(cands, x[1]), -len(x[1])))
    return [g for _cost, g in vals[:keep]]
def _scarce_shadow_bundle_exact(cands, output, task_count, deadline):
    groups = _output_to_groups(cands, output)
    if not _valid_groups_full(cands, groups, task_count):
        return output
    old_cost = sum((_group_expected_cost(cands, g) for g in groups))
    task_deg = [0] * task_count
    for c in cands:
        for t in c['tasks']:
            task_deg[t] += 1
    price = defaultdict(float)
    for c in cands:
        val = 0.0
        for t in c['tasks']:
            val += 1.0 / max(1.0, task_deg[t] ** 0.5)
        val *= max(0.01, c['p'])
        if val > price[c['cidx']]:
            price[c['cidx']] = val
    max_price = max(price.values()) if price else 1.0
    for k in list(price.keys()):
        price[k] = price[k] / max_price
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        by_mask[c['mask']].append(i)
    rows = []
    seen = set()
    for mask, arr in by_mask.items():
        k = _popcount(mask)
        if k <= 0:
            continue
        mr = 3 if k >= 2 else 2
        keep = 5 if k >= 2 else 2
        for g in _mask_group_variants(cands, arr, set(), mr, keep):
            cm = 0
            shp = 0.0
            for i in g:
                ci = cands[i]['cidx']
                cm |= 1 << ci
                shp += price.get(ci, 0.0)
            key = (mask, tuple(sorted((cands[i]['cidx'] for i in g))))
            if key in seen:
                continue
            seen.add(key)
            cost = _group_expected_cost(cands, g)
            proxy = cost + 4.0 * shp - 3.0 * max(0, k - 1)
            rows.append((mask, cm, cost, proxy, tuple(g)))
    if not rows:
        return output
    by_task = [[] for _ in range(task_count)]
    for rid, r in enumerate(rows):
        m = r[0]
        while m:
            b = m & -m
            by_task[b.bit_length() - 1].append(rid)
            m -= b
    for t in range(task_count):
        if not by_task[t]:
            return output
        by_task[t].sort(key=lambda rid: (rows[rid][3] / max(1, _popcount(rows[rid][0])), rows[rid][2], -_popcount(rows[rid][0])))
        by_task[t] = by_task[t][:120]
    all_mask = (1 << task_count) - 1
    states = [(0, 0, 0.0, 0.0, ())]
    order = list(range(task_count))
    order.sort(key=lambda t: len(by_task[t]))
    limit = 3200 if task_count >= 35 else 4500
    for t in order:
        if time.time() >= deadline:
            break
        bit = 1 << t
        ns = []
        for mask, cmask, cost, proxy, path in states:
            if mask & bit:
                ns.append((mask, cmask, cost, proxy, path))
                continue
            for rid in by_task[t]:
                rmask, rcm, rcost, rproxy, g = rows[rid]
                if mask & rmask or cmask & rcm:
                    continue
                ns.append((mask | rmask, cmask | rcm, cost + rcost, proxy + rproxy, path + (rid,)))
        if not ns:
            return output
        best = {}
        for item in ns:
            mask, cmask, cost, proxy, path = item
            key = (mask, cmask)
            old = best.get(key)
            if old is None or proxy < old[3]:
                best[key] = item
        states = list(best.values())
        if len(states) > limit:
            states.sort(key=lambda x: (-_popcount(x[0]), x[3] + 50.0 * (task_count - _popcount(x[0])), x[2], len(x[4])))
            states = states[:limit]
    best_path = None
    best_cost = old_cost
    for mask, cmask, cost, proxy, path in states:
        if mask == all_mask and cost < best_cost - 1e-09:
            best_cost = cost
            best_path = path
    if best_path is None:
        return output
    ng = [list(rows[rid][4]) for rid in best_path]
    if not _valid_groups_full(cands, ng, task_count):
        return output
    new_out = _groups_to_output(cands, ng)
    nc, nv, _ = _output_expected_cost(cands, new_out)
    if nv == task_count and nc + 1e-09 < old_cost:
        return new_out
    return output
def _cycle_reassign_fixed_skeleton(cands, output, task_count, st, deadline):
    if st.get('low') or st.get('scarce') or task_count <= 8 or (time.time() >= deadline):
        return output
    groups = _output_to_groups(cands, output)
    if not groups:
        return output
    used_mask = 0
    for g in groups:
        if not g:
            return output
        first = cands[g[0]]
        if first['k'] != 1:
            return output
        used_mask |= first['mask']
        for i in g:
            if cands[i]['mask'] != first['mask']:
                return output
    if _popcount(used_mask) != task_count:
        return output
    by_tc = {}
    for i, c in enumerate(cands):
        if c['k'] == 1:
            by_tc[c['tasks'][0], c['cidx']] = i
    assign = {}
    for g in groups:
        t = cands[g[0]]['tasks'][0]
        assign[t] = [cands[i]['cidx'] for i in g]
    if len(assign) != task_count:
        return output
    all_cids = []
    for cids in assign.values():
        all_cids.extend(cids)
    if len(all_cids) != len(set(all_cids)):
        return output
    for t in range(task_count):
        for cid in all_cids:
            if (t, cid) not in by_tc:
                return output
    cost_cache = {}
    def gcost(t, cids):
        key = (t, tuple(cids))
        v = cost_cache.get(key)
        if v is not None:
            return v
        ids = [by_tc[t, cid] for cid in key[1]]
        v = _group_expected_cost(cands, ids)
        cost_cache[key] = v
        return v
    def total_cost():
        return sum((gcost(t, cids) for t, cids in assign.items()))
    old_total = total_cost()
    perms3 = [(1, 2, 0), (2, 0, 1), (0, 2, 1), (1, 0, 2), (2, 1, 0)]
    for _round in range(2):
        if time.time() >= deadline:
            break
        costs = dict(((t, gcost(t, assign[t])) for t in range(task_count)))
        best_delta = 1e-09
        best_op = None
        for a in range(task_count - 2):
            if time.time() >= deadline:
                break
            la = assign[a]
            for b in range(a + 1, task_count - 1):
                lb = assign[b]
                for d in range(b + 1, task_count):
                    old = costs[a] + costs[b] + costs[d]
                    ld = assign[d]
                    for ia, ca in enumerate(la):
                        for ib, cb in enumerate(lb):
                            for idd, cd in enumerate(ld):
                                selected = (ca, cb, cd)
                                for pi in perms3:
                                    na = la[:]
                                    nb = lb[:]
                                    nd = ld[:]
                                    na[ia] = selected[pi[0]]
                                    nb[ib] = selected[pi[1]]
                                    nd[idd] = selected[pi[2]]
                                    val = gcost(a, na) + gcost(b, nb) + gcost(d, nd)
                                    delta = old - val
                                    if delta > best_delta:
                                        best_delta = delta
                                        best_op = (a, b, d, ia, ib, idd, selected, pi)
        if best_op is None:
            break
        a, b, d, ia, ib, idd, selected, pi = best_op
        assign[a][ia] = selected[pi[0]]
        assign[b][ib] = selected[pi[1]]
        assign[d][idd] = selected[pi[2]]
    if time.time() < deadline:
        costs = dict(((t, gcost(t, assign[t])) for t in range(task_count)))
        top = sorted(range(task_count), key=lambda t: costs[t], reverse=True)[:16]
        windows = []
        for a in range(len(top) - 3):
            for b in range(a + 1, len(top) - 2):
                for c in range(b + 1, len(top) - 1):
                    for d in range(c + 1, len(top)):
                        tw = (top[a], top[b], top[c], top[d])
                        windows.append((costs[tw[0]] + costs[tw[1]] + costs[tw[2]] + costs[tw[3]], tw))
        windows.sort(reverse=True)
        windows = windows[:1000]
        perms4 = []
        basep = (0, 1, 2, 3)
        for p0 in range(4):
            for p1 in range(4):
                if p1 == p0:
                    continue
                for p2 in range(4):
                    if p2 == p0 or p2 == p1:
                        continue
                    p3 = 6 - p0 - p1 - p2
                    p = (p0, p1, p2, p3)
                    if p != basep:
                        perms4.append(p)
        best_delta = 1e-09
        best_op = None
        for _sumc, tw in windows:
            if time.time() >= deadline:
                break
            lists = [assign[tw[0]], assign[tw[1]], assign[tw[2]], assign[tw[3]]]
            if len(lists[0]) * len(lists[1]) * len(lists[2]) * len(lists[3]) > 96:
                continue
            old = costs[tw[0]] + costs[tw[1]] + costs[tw[2]] + costs[tw[3]]
            for i0 in range(len(lists[0])):
                for i1 in range(len(lists[1])):
                    for i2 in range(len(lists[2])):
                        for i3 in range(len(lists[3])):
                            pos = (i0, i1, i2, i3)
                            selected = (lists[0][i0], lists[1][i1], lists[2][i2], lists[3][i3])
                            for pi in perms4:
                                val = 0.0
                                for x in range(4):
                                    ng = lists[x][:]
                                    ng[pos[x]] = selected[pi[x]]
                                    val += gcost(tw[x], ng)
                                delta = old - val
                                if delta > best_delta:
                                    best_delta = delta
                                    best_op = (tw, pos, selected, pi)
        if best_op is not None:
            tw, pos, selected, pi = best_op
            for x in range(4):
                assign[tw[x]][pos[x]] = selected[pi[x]]
    new_groups = []
    for t in sorted(assign.keys()):
        g = [by_tc[t, cid] for cid in assign[t]]
        new_groups.append(g)
    new_out = _groups_to_output(cands, new_groups)
    old_cost, old_cov, _ = _output_expected_cost(cands, output)
    new_cost, new_cov, _ = _output_expected_cost(cands, new_out)
    if new_cov == task_count and new_cost + 1e-09 < old_cost:
        return new_out
    return output
def _row_option_beam_output(cands, task_count, st, deadline, limit):
    if time.time() >= deadline:
        return []
    max_r = MULTI_LOW_MAX_RIDERS if st.get('low') else 3 if st.get('route_scarce') else MULTI_NORMAL_MAX_RIDERS
    keep = 10 if st.get('low') else 6
    scan = 34 if st.get('low') else 24
    by_mask = defaultdict(list)
    for i, c in enumerate(cands):
        by_mask[c['mask']].append(i)
    rows = []
    seen = set()
    def add(mask, g):
        if not g:
            return
        used = set()
        gg = []
        for i in sorted(g, key=lambda x: (cands[x]['score'], -cands[x]['p'])):
            if cands[i]['cidx'] in used:
                continue
            used.add(cands[i]['cidx'])
            gg.append(i)
            if len(gg) >= max_r:
                break
        if not gg:
            return
        key = (mask, tuple(sorted((cands[i]['cidx'] for i in gg))))
        if key in seen:
            return
        seen.add(key)
        cm = 0
        for i in gg:
            cm |= 1 << cands[i]['cidx']
        rows.append((mask, cm, _group_expected_cost(cands, gg), tuple(gg), _group_fail_prob(cands, gg)))
    for mask, arr in by_mask.items():
        if time.time() >= deadline:
            break
        orders = [sorted(arr, key=lambda i: (cands[i]['score'], -cands[i]['p'], cands[i]['cost']))[:scan], sorted(arr, key=lambda i: (-cands[i]['p'], cands[i]['score'], cands[i]['cost']))[:scan], sorted(arr, key=lambda i: (cands[i]['cost'] / cands[i]['k'], cands[i]['score'], -cands[i]['p']))[:scan], sorted(arr, key=lambda i: (-(cands[i]['p'] * (BASE * cands[i]['k'] - cands[i]['score'])), cands[i]['score']))[:scan]]
        base = len(rows)
        for order in orders:
            g = []
            used = set()
            for i in order:
                if cands[i]['cidx'] in used:
                    continue
                g.append(i)
                used.add(cands[i]['cidx'])
                add(mask, g)
                if len(g) >= max_r:
                    break
            for seed in order[:3]:
                g = [seed]
                used = set([cands[seed]['cidx']])
                add(mask, g)
                while len(g) < max_r:
                    old = _group_expected_cost(cands, g)
                    bi = None
                    bg = 1e-09
                    for i in order:
                        if cands[i]['cidx'] in used:
                            continue
                        gain = old - _group_expected_cost(cands, g + [i])
                        if gain > bg:
                            bg = gain
                            bi = i
                    if bi is None:
                        break
                    g.append(bi)
                    used.add(cands[bi]['cidx'])
                    add(mask, g)
        local = rows[base:]
        if len(local) > keep:
            local.sort(key=lambda r: (r[2] / max(1, _popcount(r[0])), r[2], r[4], -len(r[3])))
            rows[:] = rows[:base] + local[:keep]
    if not rows:
        return []
    by_task = [[] for _ in range(task_count)]
    for rid, r in enumerate(rows):
        m = r[0]
        while m:
            b = m & -m
            t = b.bit_length() - 1
            m -= b
            by_task[t].append(rid)
    for t in range(task_count):
        if not by_task[t]:
            return []
        by_task[t].sort(key=lambda rid: (rows[rid][2] / max(1, _popcount(rows[rid][0])), rows[rid][4], -len(rows[rid][3])))
        by_task[t] = by_task[t][:160]
    order = list(range(task_count))
    order.sort(key=lambda t: len(by_task[t]))
    states = [(0, 0, 0.0, ())]
    for t in order:
        if time.time() >= deadline:
            break
        bit = 1 << t
        ns = []
        for mask, cmask, cost, sel in states:
            if mask & bit:
                ns.append((mask, cmask, cost, sel))
                continue
            for rid in by_task[t]:
                rmask, rcmask, rcost, _g, _f = rows[rid]
                if mask & rmask or cmask & rcmask:
                    continue
                ns.append((mask | rmask, cmask | rcmask, cost + rcost, sel + (rid,)))
        if not ns:
            return []
        best = {}
        for it in ns:
            key = (it[0], it[1])
            old = best.get(key)
            if old is None or it[2] < old[2]:
                best[key] = it
        states = list(best.values())
        if len(states) > limit:
            states.sort(key=lambda x: (-_popcount(x[0]), x[2] + BASE * (task_count - _popcount(x[0])), len(x[3])))
            states = states[:limit]
    best = None
    bk = None
    for mask, cmask, cost, sel in states:
        k = (_popcount(mask), -cost, -len(sel))
        if bk is None or k > bk:
            bk = k
            best = sel
    if not best:
        return []
    out = []
    used_t = 0
    used_c = set()
    for rid in best:
        mask, _cm, _co, group, _fail = rows[rid]
        if used_t & mask:
            continue
        couriers = []
        ok = True
        for i in group:
            if cands[i]['cidx'] in used_c:
                ok = False
                break
            couriers.append(cands[i]['courier'])
        if ok and couriers:
            out.append((cands[group[0]]['task_str'], couriers))
            used_t |= mask
            for i in group:
                used_c.add(cands[i]['cidx'])
    return out if _popcount(used_t) == task_count else []
def _low_global_backup_matching(cands, output, task_count, deadline):
    groups = _output_to_groups(cands, output)
    if not groups or time.time() >= deadline:
        return output
    mt = 0
    for g in groups:
        if not g:
            return output
        mt |= cands[g[0]]['mask']
    if _popcount(mt) != task_count:
        return output
    old_cost, old_cov, _old_pairs = _output_expected_cost(cands, output)
    base_groups = [[g[0]] for g in groups]
    used = set()
    for g in base_groups:
        used.add(cands[g[0]]['cidx'])
    by_m = defaultdict(list)
    for i, c in enumerate(cands):
        by_m[c['mask']].append(i)
    for m in by_m:
        by_m[m].sort(key=lambda i: (cands[i]['score'], cands[i]['cost'], -cands[i]['p']))
    max_r = MULTI_LOW_MAX_RIDERS
    rounds = 0
    while rounds < max_r - 1 and time.time() < deadline:
        rounds += 1
        rows = []
        rmap = []
        ridmap = {}
        edges = []
        scale = 1000000
        for gi, g in enumerate(base_groups):
            if len(g) >= max_r:
                continue
            cur = _group_expected_cost(cands, g)
            local = set(cands[x]['cidx'] for x in g)
            checked = 0
            cand_edges = []
            for i in by_m.get(cands[g[0]]['mask'], []):
                cc = cands[i]['cidx']
                if cc in used or cc in local:
                    continue
                gain = cur - _group_expected_cost(cands, g + [i])
                checked += 1
                if gain > 1e-09:
                    cand_edges.append((gain, i, cc))
                if checked >= 90:
                    break
            if cand_edges:
                ri = len(rmap)
                rmap.append(gi)
                cand_edges.sort(reverse=True)
                for gain, i, cc in cand_edges[:32]:
                    if cc not in ridmap:
                        ridmap[cc] = len(ridmap)
                    edges.append((ri, ridmap[cc], -int(gain * scale), i))
        R = len(rmap); C = len(ridmap)
        if not edges:
            break
        n = 1 + R + C + 1; src = 0; rb = 1; cb = rb + R; sink = n - 1
        gr = [[] for _ in range(n)]
        def add(u, v, cap, cost, idx):
            gr[u].append([v, cap, cost, len(gr[v]), idx])
            gr[v].append([u, 0, -cost, len(gr[u]) - 1, -1])
        for r in range(R):
            add(src, rb + r, 1, 0, -1)
        for r, c, co, idx in edges:
            add(rb + r, cb + c, 1, co, idx)
        for c in range(C):
            add(cb + c, sink, 1, 0, -1)
        changed = False
        while time.time() < deadline:
            INF = 10 ** 18
            dist = [INF] * n; pv = [-1] * n; pe = [-1] * n; inq = [False] * n
            dist[src] = 0; q = deque([src]); inq[src] = True
            while q:
                u = q.popleft(); inq[u] = False
                for ei, e in enumerate(gr[u]):
                    if e[1] <= 0:
                        continue
                    v = e[0]; nd = dist[u] + e[2]
                    if nd < dist[v]:
                        dist[v] = nd; pv[v] = u; pe[v] = ei
                        if not inq[v]:
                            q.append(v); inq[v] = True
            if dist[sink] >= -1:
                break
            v = sink
            while v != src:
                u = pv[v]; ei = pe[v]; e = gr[u][ei]
                e[1] -= 1; gr[v][e[3]][1] += 1; v = u
            changed = True
        if not changed:
            break
        added = 0
        for r in range(R):
            u = rb + r
            for e in gr[u]:
                if e[4] >= 0 and e[1] == 0:
                    gi = rmap[r]; idx = e[4]; cc = cands[idx]['cidx']
                    if cc not in used:
                        base_groups[gi].append(idx); base_groups[gi].sort(key=lambda x: (cands[x]['score'], -cands[x]['p']))
                        used.add(cc); added += 1
                    break
        if added <= 0:
            break
    new_out = _groups_to_output(cands, base_groups)
    nc, nv, _np = _output_expected_cost(cands, new_out)
    if nv == task_count and nc + 1e-09 < old_cost:
        return new_out
    return output
def _local3_exact_refine(cands, output, task_count, deadline, rounds=2, cap=260):
    if time.time() >= deadline or task_count <= 8:
        return output
    groups = _output_to_groups(cands, output)
    if not groups:
        return output
    mt = 0
    for g in groups:
        if not g:
            return output
        mt |= cands[g[0]]['mask']
    if _popcount(mt) != task_count:
        return output
    by_pair = dict(((c['mask'], c['cidx']), i) for i, c in enumerate(cands))
    def gc(g):
        return _group_expected_cost(cands, g)
    def ok(gs):
        ut = 0; uc = set()
        for g in gs:
            if not g:
                return False
            m = cands[g[0]]['mask']
            if ut & m:
                return False
            ut |= m
            for i in g:
                if cands[i]['mask'] != m:
                    return False
                ci = cands[i]['cidx']
                if ci in uc:
                    return False
                uc.add(ci)
        return _popcount(ut) == task_count
    def exact(inds):
        tb = []; seen = 0; free = []; old = 0.0
        for gi in inds:
            g = groups[gi]; old += gc(g); m = cands[g[0]]['mask']
            while m:
                b = m & -m; t = b.bit_length() - 1; m -= b
                if not ((seen >> t) & 1):
                    seen |= 1 << t; tb.append(t)
            for i in g:
                ci = cands[i]['cidx']
                if ci not in free:
                    free.append(ci)
        tb.sort(); free.sort()
        lt = dict((t, j) for j, t in enumerate(tb)); lc = dict((c, j) for j, c in enumerate(free))
        full = (1 << len(tb)) - 1
        masks = []
        for t in tb:
            masks.append(1 << t)
        for a in range(len(tb)):
            for b in range(a + 1, len(tb)):
                masks.append((1 << tb[a]) | (1 << tb[b]))
        rows = []; by = [[] for _ in tb]
        for mask in masks:
            lm = 0; mm = mask
            while mm:
                b = mm & -mm; lm |= 1 << lt[b.bit_length() - 1]; mm -= b
            arr = []
            for cid in free:
                idx = by_pair.get((mask, cid))
                if idx is not None:
                    arr.append((cid, idx))
            loc = []
            n = len(arr); mr = min(4, n)
            for r in range(1, mr + 1):
                for comb in itertools.combinations(range(n), r):
                    cm = 0; ids = []
                    for z in comb:
                        cid, idx = arr[z]; cm |= 1 << lc[cid]; ids.append(idx)
                    ids = tuple(ids); loc.append((gc(ids), lm, cm, ids))
            loc.sort(key=lambda x: (x[0], _popcount(x[2])))
            for row in loc[:80]:
                rid = len(rows); rows.append(row); mm = row[1]
                while mm:
                    b = mm & -mm; by[b.bit_length() - 1].append(rid); mm -= b
        memo = {}
        def dfs(tm, cm):
            if tm == full:
                return (0.0, ())
            key = (tm, cm)
            v = memo.get(key)
            if v is not None:
                return v
            rem = full & ~tm; opts = None; cnt = 10 ** 9; mm = rem
            while mm:
                b = mm & -mm; j = b.bit_length() - 1; mm -= b; os = []
                for rid in by[j]:
                    co, lm, rcm, ids = rows[rid]
                    if lm & tm or rcm & cm:
                        continue
                    os.append(rid)
                if len(os) < cnt:
                    cnt = len(os); opts = os
                    if cnt <= 1:
                        break
            if not opts:
                return (10 ** 100, ())
            best = (10 ** 100, ())
            for rid in opts:
                co, lm, rcm, ids = rows[rid]
                sub, path = dfs(tm | lm, cm | rcm); tot = co + sub
                if tot < best[0]:
                    best = (tot, (rid,) + path)
            memo[key] = best; return best
        nc, path = dfs(0, 0)
        if nc + 1e-09 < old:
            return old - nc, [list(rows[r][3]) for r in path]
        return 0.0, None
    def makewins():
        maskrow = {}; usedrow = {}; costs = []
        for gi, g in enumerate(groups):
            maskrow[cands[g[0]]['mask']] = gi; costs.append(gc(g))
            for i in g:
                usedrow[cands[i]['cidx']] = gi
        bm = defaultdict(list); cmasks = defaultdict(set)
        for i, c in enumerate(cands):
            bm[c['mask']].append(i); cmasks[c['cidx']].add(c['mask'])
        for m in bm:
            bm[m].sort(key=lambda i: (cands[i]['score'], cands[i]['cost'], -cands[i]['p']))
        wins = {}
        for gi, g in enumerate(groups):
            m = cands[g[0]]['mask']; cg = costs[gi]
            for cand in bm.get(m, [])[:40]:
                ccid = cands[cand]['cidx']; sr = usedrow.get(ccid)
                if sr is None or sr == gi:
                    continue
                for pos, old in enumerate(g):
                    if cands[old]['cidx'] == ccid:
                        continue
                    ng = g[:]; ng[pos] = cand
                    if len(set(cands[x]['cidx'] for x in ng)) < len(ng):
                        continue
                    gain1 = cg - gc(ng); oc = cands[old]['cidx']
                    for mm in cmasks.get(oc, ()):
                        hr = maskrow.get(mm)
                        if hr is None or hr == gi or hr == sr:
                            continue
                        idx = by_pair.get((cands[groups[hr][0]]['mask'], oc))
                        if idx is None or any(cands[x]['cidx'] == oc for x in groups[hr]):
                            continue
                        gain2 = costs[hr] - gc(groups[hr] + [idx])
                        sg = [x for x in groups[sr] if cands[x]['cidx'] != ccid]
                        gain3 = costs[sr] - gc(sg) if sg else -999.0
                        score = gain1 + gain2 + gain3
                        w = tuple(sorted((gi, sr, hr)))
                        if score > wins.get(w, (-1e99,))[0]:
                            wins[w] = (score, w)
        top = [i for i, _c in sorted(enumerate(costs), key=lambda x: -x[1])[:14]]
        for w in itertools.combinations(top, 3):
            wins.setdefault(tuple(sorted(w)), (0.0, tuple(sorted(w))))
        return [w for _s, w in sorted(wins.values(), reverse=True)]
    old_out = _groups_to_output(cands, groups); oldc, oldv, _ = _output_expected_cost(cands, old_out)
    for _ in range(rounds):
        if time.time() >= deadline:
            break
        bestg = 0.0; bestw = None; bestng = None
        for w in makewins()[:cap]:
            if time.time() >= deadline:
                break
            gain, ng = exact(w)
            if gain > bestg + 1e-09:
                bestg = gain; bestw = w; bestng = ng
        if bestng is None:
            break
        rem = set(bestw)
        cand_groups = [g for i, g in enumerate(groups) if i not in rem] + bestng
        if not ok(cand_groups):
            break
        groups = cand_groups
    new_out = _groups_to_output(cands, groups)
    nc, nv, _ = _output_expected_cost(cands, new_out)
    if nv == task_count and nc + 1e-09 < oldc:
        return new_out
    return output
def _window3_fast_exact_repair_output(cands, output, task_count, st, deadline):
    if st.get('low') or st.get('scarce') or task_count <= 8 or time.time() >= deadline:
        return output
    groups = _output_to_groups(cands, output)
    if len(groups) < 3:
        return output
    used_t = 0
    used_c = set()
    for g in groups:
        if not g:
            return output
        m = cands[g[0]]['mask']
        if used_t & m:
            return output
        used_t |= m
        for i in g:
            if cands[i]['mask'] != m:
                return output
            cid = cands[i]['cidx']
            if cid in used_c:
                return output
            used_c.add(cid)
    if _popcount(used_t) != task_count:
        return output
    by_mask_c = defaultdict(dict)
    for i, c in enumerate(cands):
        old = by_mask_c[c['mask']].get(c['cidx'])
        if old is None or c['score'] < cands[old]['score']:
            by_mask_c[c['mask']][c['cidx']] = i
    def submasks(mask):
        s = mask
        while s:
            yield s
            s = (s - 1) & mask
    variant_cache = {}
    def variants(mask, allowed):
        key = (mask, tuple(allowed))
        got = variant_cache.get(key)
        if got is not None:
            return got
        d = by_mask_c.get(mask)
        if not d:
            variant_cache[key] = []
            return []
        arr = [d[cid] for cid in allowed if cid in d]
        out = []
        max_r = min(4, len(arr))
        for r in range(1, max_r + 1):
            for comb in itertools.combinations(arr, r):
                cmask = 0
                for i in comb:
                    cmask |= 1 << cands[i]['cidx']
                out.append((_group_expected_cost(cands, comb), mask, cmask, tuple(comb)))
        out.sort(key=lambda x: (x[0], -_popcount(x[1]), len(x[3])))
        out = out[:12]
        variant_cache[key] = out
        return out
    def exact_window(win):
        task_mask = 0
        allowed = []
        seen_c = set()
        old_cost = 0.0
        for gi in win:
            g = groups[gi]
            old_cost += _group_expected_cost(cands, g)
            task_mask |= cands[g[0]]['mask']
            for i in g:
                cid = cands[i]['cidx']
                if cid not in seen_c:
                    seen_c.add(cid)
                    allowed.append(cid)
        rows = []
        allowed_key = tuple(allowed)
        for m in submasks(task_mask):
            rows.extend(variants(m, allowed_key))
        if not rows:
            return None, 0.0
        rows.sort(key=lambda x: (x[0], -_popcount(x[1])))
        by_bit = defaultdict(list)
        for rid, row in enumerate(rows):
            mm = row[1]
            while mm:
                b = mm & -mm
                by_bit[b].append(rid)
                mm -= b
        best_cost = [old_cost - 1e-9]
        best_sel = [None]
        def choose(mask):
            rem = task_mask & (~mask)
            best_opts = None
            mm = rem
            while mm:
                b = mm & -mm
                opts = []
                for rid in by_bit[b]:
                    row = rows[rid]
                    if row[1] & mask:
                        continue
                    opts.append(rid)
                if best_opts is None or len(opts) < len(best_opts):
                    best_opts = opts
                mm -= b
            return best_opts or []
        def dfs(mask, cmask, cost, picked):
            if cost >= best_cost[0] or time.time() >= deadline:
                return
            if mask == task_mask:
                best_cost[0] = cost
                best_sel[0] = list(picked)
                return
            for rid in choose(mask)[:36]:
                row = rows[rid]
                if row[1] & mask:
                    continue
                if row[2] & cmask:
                    continue
                picked.append(row[3])
                dfs(mask | row[1], cmask | row[2], cost + row[0], picked)
                picked.pop()
        dfs(0, 0, 0.0, [])
        if best_sel[0] is None:
            return None, 0.0
        return [list(g) for g in best_sel[0]], old_cost - best_cost[0]
    improved = False
    rounds = 0
    while rounds < 60 and time.time() < deadline:
        rounds += 1
        costs = [_group_expected_cost(cands, g) for g in groups]
        top = sorted(range(len(groups)), key=lambda i: costs[i], reverse=True)[:40]
        accepted = False
        checked = 0
        for win in itertools.combinations(top, 3):
            checked += 1
            if checked % 128 == 0 and time.time() >= deadline:
                break
            new_groups, gain = exact_window(win)
            if gain > 1e-9:
                drop = set(win)
                groups = [g for idx, g in enumerate(groups) if idx not in drop] + new_groups
                improved = True
                accepted = True
                break
        if not accepted:
            break
    if not improved:
        return output
    new_out = _groups_to_output(cands, groups)
    old_cost, old_cov, _old_pairs = _output_expected_cost(cands, output)
    new_cost, new_cov, _new_pairs = _output_expected_cost(cands, new_out)
    if new_cov == task_count and new_cost + 1e-9 < old_cost:
        return new_out
    return output
def solve(input_text):
    global USE_SEQ_GROUP_COST
    start = time.time()
    deadline = start + TIME_LIMIT
    raw, task_count, courier_count = _parse(input_text)
    if not raw:
        return []
    cands = _compress(raw)
    st = _stats(cands, task_count, courier_count)
    USE_SEQ_GROUP_COST = bool(task_count <= 8)
    strong_scarce = st.get('scarce') and courier_count <= task_count
    route_scarce = bool(st.get('route_scarce') or (st.get('scarce') and courier_count <= int(task_count * 1.8 + 0.5)))
    search_st = dict(st)
    search_st['scarce'] = bool(strong_scarce or route_scarce)
    search_st['strong_scarce'] = bool(strong_scarce)
    search_st['route_scarce'] = bool(route_scarce)
    pool = []
    output_pool = []
    single = _mcmf_single(cands, task_count, courier_count)
    if single:
        pool.append(('single_c100_mcmf', single))
    if task_count <= 18 and time.time() < deadline - 0.2:
        ex = _exact_small_unique(cands, task_count, courier_count, min(deadline - 0.1, time.time() + 2.3), single)
        if ex:
            pool.append(('small_exact_c100', ex))
        if time.time() < deadline - 0.2:
            dp = _exact_small_dp_unique(cands, task_count, min(deadline - 0.1, time.time() + 2.0), ex or single)
            if dp:
                pool.append(('small_dp_c100', dp))
        if task_count <= 8 and time.time() < deadline - 0.2:
            tiny_out = _small_multi_group_exact_output(cands, task_count, search_st, min(deadline - 0.1, time.time() + 2.2))
            if tiny_out:
                output_pool.append(('tiny_multi_group_exact', tiny_out))
    skip_large_normal_greedy = not st.get('low') and (not route_scarce) and task_count >= 35
    if not skip_large_normal_greedy:
        for idx, sol in enumerate(_greedy_candidates(cands, task_count)):
            if sol:
                pool.append(('greedy_%02d' % idx, sol))
    if st.get('low') or route_scarce:
        r = _row_first_candidate(cands, task_count)
        if r:
            pool.append(('row_first_hist', r))
        if st.get('low'):
            mp = _multi_potential_candidate(cands, task_count, search_st)
            if mp:
                pool.append(('multi_potential', mp))
            mbf = _multi_bundle_first_candidate(cands, task_count, search_st)
            if mbf:
                pool.append(('multi_bundle_first', mbf))
            if time.time() < deadline - 0.6:
                mb = _multi_model_beam_candidate(cands, task_count, search_st, min(deadline - 0.25, time.time() + 1.55), 3600)
                if mb:
                    pool.append(('multi_model_beam', mb))
            if (not st.get('low')) and (st.get('low') or route_scarce) and time.time() < deadline - 0.55:
                mout = _multi_model_beam_output(cands, task_count, search_st, min(deadline - 0.2, time.time() + 1.35), 2600)
                if mout:
                    output_pool.append(('multi_model_output', mout))
        if (st.get('low') or route_scarce) and time.time() < deadline - 0.45:
            rout = _row_option_beam_output(cands, task_count, search_st, min(deadline - 0.18, time.time() + (1.35 if st.get('low') else 1.1)), 1900 if st.get('low') else 1400)
            if rout:
                output_pool.append(('row_option_seq' if st.get('low') else 'row_option_scarce', rout))
        if (not st.get('low')) and time.time() < deadline - 0.5:
            limit = 1600 if task_count >= 35 else 2400
            beam = _beam_cover_unique(cands, task_count, min(deadline - 0.25, time.time() + (0.95 if route_scarce else 1.05)), limit)
            if beam:
                pool.append(('beam_cover_unique', beam))
    best = []
    bestk = None
    for _name, sol in pool:
        clean = _clean(sol, cands)
        if not clean:
            continue
        k = _key(clean, cands)
        if bestk is None or k > bestk:
            bestk = k
            best = clean
    debug_extra = []
    if best and (not search_st.get('low')) and (search_st.get('route_scarce') or task_count < 35) and time.time() < deadline - 0.45:
        b = _bundle_savings_unique(cands, best, task_count, min(deadline - 0.25, time.time() + 1.05))
        if b:
            debug_extra.append(('bundle_savings', b))
        if b and _key(b, cands) > _key(best, cands):
            best = _clean(b, cands)
    best = _complete_unique(cands, best, task_count)
    if SCENE_ADAPTIVE_MULTI_COURIER and time.time() < deadline - 0.1:
        if (not search_st.get('low')) and (not search_st.get('route_scarce')) and task_count >= 35:
            out = _safe_output_multi(cands, best, task_count, search_st, min(deadline - 0.05, time.time() + 0.22))
        else:
            choose_seconds = 1.7 if search_st.get('low') or search_st.get('scarce') else 0.8 if task_count >= 35 else 1.35 if task_count >= 19 else 2.2
            out = _choose_best_multi_output(cands, pool + debug_extra + [('final', best)], task_count, search_st, min(deadline - 0.05, time.time() + choose_seconds), output_pool)
        if out:
            if task_count <= 8:
                return out
            if search_st.get('low'):
                return _low_global_backup_matching(cands, out, task_count, min(deadline, time.time() + 0.85))
            if search_st.get('route_scarce'):
                so = _scarce_shadow_bundle_exact(cands, out, task_count, min(deadline, time.time() + 1.05))
                return so
            out = _reassign_fixed_skeleton(cands, out, task_count, search_st, min(deadline, time.time() + 0.75))
            cycle_deadline = min(deadline, time.time() + (1.45 if task_count >= 35 else 1.45))
            out = _cycle_reassign_fixed_skeleton(cands, out, task_count, search_st, cycle_deadline)
            if task_count >= 35:
                return _window3_fast_exact_repair_output(cands, out, task_count, search_st, min(deadline, time.time() + 1.35))
            return _local3_exact_refine(cands, out, task_count, min(deadline, time.time() + 0.45), 1, 40)
    out = _safe_output_multi(cands, best, task_count, search_st, deadline)
    if task_count <= 8:
        return out
    if search_st.get('low'):
        return _low_global_backup_matching(cands, out, task_count, min(deadline, time.time() + 0.85))
    if search_st.get('route_scarce'):
        so = _scarce_shadow_bundle_exact(cands, out, task_count, min(deadline, time.time() + 1.05))
        return so
    out = _reassign_fixed_skeleton(cands, out, task_count, search_st, min(deadline, time.time() + 0.75))
    cycle_deadline = min(deadline, time.time() + (1.45 if task_count >= 35 else 1.45))
    out = _cycle_reassign_fixed_skeleton(cands, out, task_count, search_st, cycle_deadline)
    if task_count >= 35:
        return _window3_fast_exact_repair_output(cands, out, task_count, search_st, min(deadline, time.time() + 1.35))
    return _local3_exact_refine(cands, out, task_count, min(deadline, time.time() + 0.45), 1, 40)
