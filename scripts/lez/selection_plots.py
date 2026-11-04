"""Read verified M0 results and draw descriptive comparisons without rerunning M0.

This module does not import the routing/GIS engine, access the network, or modify
the source bundles. A published snapshot also works after a code-only clone.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .common import (atomic_bytes, atomic_json, cached_manifest, digest, file_hash,
                     input_path, now, relative, write_csv)


PUBLISHED = 'docs/results/m0_2026_11_02'
X_METRICS = {
    'unique_rc_coverage_fraction': (100.0, 'Độ phủ mạng RC không trùng (%)', 'percentage_point'),
    'traversed_length_m': (0.001, 'Tổng chiều dài lượt đi (km)', 'km'),
}
SOURCE_KEYS = ('fingerprint', 'valid_samples', 'baseline_selected_ids',
               'baseline_metrics', 'quota', 'intersection_quota', 'comparison')


@dataclass
class ComparisonData:
    work: Path
    source: str
    report: dict
    protocol: dict
    frame: pd.DataFrame
    input_hashes: dict


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _equivalent(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_equivalent(v, b[k]) for k, v in a.items())
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return isinstance(b, (int, float)) and math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)
    return a == b


def _validate(frame, report, protocol):
    required = {'sample_id', 'route_ids', 'D_combined', 'route_count', 'inside', 'outside',
                'traversed_length_m', 'unique_rc_length_m', 'unique_rc_coverage_fraction'}
    if not required <= set(frame):
        raise ValueError('M0 CSV thiếu cột: ' + ', '.join(sorted(required - set(frame))))
    if report.get('status') != 'completed_pre_survey_random_baseline':
        raise ValueError('Báo cáo M0 chưa hoàn tất; chạy notebook 10 trước.')
    if frame.empty or len(frame) != report['valid_samples'] or len(frame) != report['comparison']['n']:
        raise ValueError('Số bộ trong CSV không khớp báo cáo M0.')
    if protocol['baseline_selected_ids'] != report['baseline_selected_ids']:
        raise ValueError('Protocol và báo cáo không cùng bộ 30.')
    if protocol['quota'] != report['quota'] or protocol['intersection_quota'] != report['intersection_quota']:
        raise ValueError('Protocol và báo cáo không cùng quota.')
    expected = Counter()
    for bucket in report['intersection_quota']:
        if len(bucket['sampling_zones']) != 1:
            raise ValueError('Biểu đồ này yêu cầu nhóm quota đơn vùng như A10/B8/C12.')
        expected[bucket['sampling_zones'][0]] += bucket['count']
    size = sum(expected.values())
    baseline = report['baseline_selected_ids']
    if len(baseline) != size or len(set(baseline)) != size or Counter(r[0] for r in baseline) != expected:
        raise ValueError('Bộ gốc không khớp quota đã khai báo.')
    ids = pd.to_numeric(frame['sample_id'], errors='raise').to_numpy(dtype=float)
    if not np.isfinite(ids).all() or np.any(ids < 1) or np.any(ids != np.floor(ids)) or len(set(ids)) != len(ids):
        raise ValueError('sample_id phải là số nguyên dương duy nhất.')
    numeric = ['D_combined', 'unique_rc_coverage_fraction', 'unique_rc_length_m',
               'traversed_length_m', 'route_count', 'inside', 'outside']
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors='raise')
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError('Giá trị không hữu hạn: ' + column)
    for column in ('D_combined', 'unique_rc_coverage_fraction'):
        if not frame[column].between(0, 1).all():
            raise ValueError(column + ' phải thuộc [0,1].')
    if (frame['traversed_length_m'] <= 0).any() or (frame['unique_rc_length_m'] < 0).any():
        raise ValueError('Chiều dài M0 không hợp lệ.')
    for key, value in (('route_count', size), ('inside', report['quota']['inside']), ('outside', report['quota']['outside'])):
        if not (frame[key] == value).all():
            raise ValueError('CSV không giữ quota: ' + key)
    for raw in frame['route_ids']:
        route_ids = str(raw).split('|')
        if len(route_ids) != size or len(set(route_ids)) != size or Counter(r[0] for r in route_ids if r) != expected:
            raise ValueError('Có bộ ngẫu nhiên sai quota hoặc lặp mã tuyến.')
    d = frame['D_combined'].to_numpy(dtype=float)
    stats = report['comparison']['D_distribution']
    for key, value in (('mean', d.mean()), ('median', np.median(d)), ('min', d.min()), ('max', d.max())):
        if not math.isclose(stats[key], float(value), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError('Thống kê D trong báo cáo không khớp CSV: ' + key)
    base = report['baseline_metrics']
    for key in ('D_combined', 'unique_rc_coverage_fraction'):
        if not math.isfinite(base[key]) or not 0 <= base[key] <= 1:
            raise ValueError('Chỉ tiêu bộ gốc không hợp lệ: ' + key)
    if not math.isfinite(base['traversed_length_m']) or base['traversed_length_m'] <= 0:
        raise ValueError('Chiều dài bộ gốc không hợp lệ.')
    if not math.isclose(base['D_combined'], report['comparison']['baseline_D'], abs_tol=1e-12):
        raise ValueError('Hai giá trị D bộ gốc không khớp.')
    tolerance = protocol['config']['comparison_tolerance']
    if not math.isfinite(tolerance) or not 0 <= tolerance <= 1e-8:
        raise ValueError('Dung sai so sánh M0 không hợp lệ.')
    count = int(np.count_nonzero(d <= base['D_combined'] + tolerance))
    if count != report['comparison']['no_higher_D_count']:
        raise ValueError('Số bộ có D không lớn hơn bộ gốc không khớp báo cáo.')


def load_comparison(work, source='auto'):
    """Prefer the local M0; fall back only when its latest pointer is absent.

    A corrupt/stale local result raises an error instead of silently switching
    to an older snapshot. This checks result hashes, not the whole GIS pipeline.
    """
    work = Path(work).resolve()
    if source not in ('auto', 'latest', 'published'):
        raise ValueError('source phải là auto, latest hoặc published.')
    pointer = work / 'reports/selection/latest_random_baseline.json'
    chosen = ('latest' if pointer.exists() else 'published') if source == 'auto' else source
    if chosen == 'latest':
        if not pointer.is_file():
            raise FileNotFoundError('Chưa có M0 tại máy. Chạy notebook 10 hoặc chọn source="published".')
        report = _read(pointer)
        directory = input_path(work, report['paths']['directory'])
        if not directory.is_relative_to(work):
            raise ValueError('Bundle M0 phải nằm trong thư mục work đã chọn.')
        manifest = cached_manifest(directory, report['fingerprint'])
        if not manifest:
            raise ValueError('Bundle M0 thiếu/hỏng/hash sai. Kiểm notebook 10; không tự chuyển bản cũ.')
        bundle_report = _read(directory / 'report.json')
        if any(report.get(k) != manifest['report'].get(k) or report.get(k) != bundle_report.get(k) for k in SOURCE_KEYS):
            raise ValueError('Con trỏ M0 không khớp báo cáo trong bundle.')
        paths = [pointer, directory / 'manifest.json', directory / 'report.json',
                 directory / 'random_sets.csv', directory / 'protocol.json']
        for key, filename in (('sets', 'random_sets.csv'), ('protocol', 'protocol.json')):
            if input_path(work, report['paths'][key]) != directory / filename:
                raise ValueError('Đường dẫn ' + key + ' không khớp bundle M0.')
        baseline_path = work / 'reports/selection/latest_selection_30.json'
        if baseline_path.is_file():
            baseline = _read(baseline_path)
            if (baseline['selected_route_ids'] != report['baseline_selected_ids']
                    or not _equivalent(baseline['metrics'], report['baseline_metrics'])):
                raise ValueError('Bộ 30 hiện tại đã đổi. Chạy lại notebook 10 trước khi so sánh latest.')
            paths.append(baseline_path)
    else:
        directory = work / PUBLISHED
        checksums = _read(directory / 'checksums.json')
        if checksums.get('algorithm') != 'sha256':
            raise ValueError('Bản M0 công bố thiếu quy tắc hash SHA-256.')
        required = {'summary.json', 'random_sets.csv', 'protocol.json', 'provenance.json'}
        if not required <= set(checksums['files']):
            raise ValueError('Bản M0 công bố thiếu hash của đầu vào cần thiết.')
        paths = [directory / 'checksums.json']
        for name, expected in checksums['files'].items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()) or file_hash(path) != expected:
                raise ValueError('Bản M0 công bố không khớp hash: ' + name)
            paths.append(path)
        report = _read(directory / 'summary.json')
        provenance = _read(directory / 'provenance.json')
        if (report['source_run_fingerprint'] != provenance['source_run_fingerprint']
                or report['baseline_selected_ids'] != provenance['baseline_selected_route_ids']):
            raise ValueError('Bản M0 công bố không khớp hồ sơ nguồn.')
        # The compact publication uses a different field name from local reports.
        report = dict(report, fingerprint=report['source_run_fingerprint'])
    protocol = _read(directory / 'protocol.json')
    frame = pd.read_csv(directory / 'random_sets.csv')
    _validate(frame, report, protocol)
    hashes = {relative(p, work): file_hash(p) for p in paths}
    return ComparisonData(work, chosen, report, protocol, frame, hashes)


def describe_comparison(data):
    d = data.frame['D_combined'].to_numpy(dtype=float)
    baseline = data.report['baseline_metrics']['D_combined']
    tolerance = data.protocol['config']['comparison_tolerance']
    lower = int(np.count_nonzero(d < baseline - tolerance))
    tied = int(np.count_nonzero(np.abs(d - baseline) <= tolerance))
    return {'source': data.source, 'fingerprint': data.report['fingerprint'],
            'random_sets': len(d), 'baseline_D': baseline, 'random_mean_D': float(d.mean()),
            'random_median_D': float(np.median(d)), 'random_min_D': float(d.min()), 'random_max_D': float(d.max()),
            'strictly_lower_D_count': lower, 'tied_D_count': tied,
            'no_higher_D_count': lower + tied, 'higher_D_count': len(d) - lower - tied,
            'no_higher_D_percent': 100 * (lower + tied) / len(d),
            'comparison_tolerance': tolerance,
            'interpretation': 'Descriptive benchmark on a fixed pool; not a p-value, field validation or proof of global optimality.'}


def d_interval_table(data, bin_width=0.02):
    """Fixed intervals cover [0,1]; only the last includes its upper endpoint."""
    if not math.isfinite(bin_width) or not 0.0001 <= bin_width <= 1:
        raise ValueError('bin_width phải thuộc [0.0001,1].')
    edges = np.r_[np.round(np.arange(0, 1, bin_width), 12), 1.0]
    counts, _ = np.histogram(data.frame['D_combined'], bins=edges)
    baseline = data.report['baseline_metrics']['D_combined']
    selected_bin = min(int(np.searchsorted(edges, baseline, side='right') - 1), len(counts) - 1)
    return pd.DataFrame({
        'D_interval': [f'[{a:.4f}, {b:.4f}' + (']' if i == len(counts) - 1 else ')')
                       for i, (a, b) in enumerate(zip(edges[:-1], edges[1:]))],
        'left': edges[:-1], 'right': edges[1:], 'count': counts,
        'percent': counts / len(data.frame) * 100,
        'contains_baseline': np.arange(len(counts)) == selected_bin,
    })


def regression_summary(data, x_metric='unique_rc_coverage_fraction'):
    if x_metric not in X_METRICS:
        raise ValueError('x_metric không được hỗ trợ: ' + str(x_metric))
    scale, _, unit = X_METRICS[x_metric]
    x = data.frame[x_metric].to_numpy(dtype=float) * scale
    y = data.frame['D_combined'].to_numpy(dtype=float)
    selected_x = data.report['baseline_metrics'][x_metric] * scale
    result = {'x_metric': x_metric, 'x_unit': unit, 'n': len(x),
              'fit_population': 'random_sets_only', 'confidence_interval': None,
              'baseline_x': selected_x, 'baseline_D': data.report['baseline_metrics']['D_combined'],
              'baseline_within_random_x_range': bool(x.min() <= selected_x <= x.max()),
              'interpretation': 'Descriptive linear association in M0; not a causal model or field inference.'}
    centered = x - x.mean()
    if len(x) < 2 or np.ptp(x) <= 1e-12:
        return dict(result, status='constant_or_insufficient_x', slope=None, intercept=None, r_squared=None)
    slope = float(np.dot(centered, y - y.mean()) / np.dot(centered, centered))
    intercept = float(y.mean() - slope * x.mean())
    fitted = intercept + slope * x
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = None if total <= 1e-24 else float(1 - np.sum((y - fitted) ** 2) / total)
    return dict(result, status='fitted', slope=slope, intercept=intercept, r_squared=r2)


def _libraries():
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import seaborn as sns
    return mpl, plt, sns


def plot_d_histogram(data, bin_width=0.02, stat='percent'):
    if stat not in ('count', 'percent'):
        raise ValueError('stat phải là count hoặc percent.')
    table = d_interval_table(data, bin_width)
    edges = np.r_[table['left'].to_numpy(), table['right'].iloc[-1]]
    description = describe_comparison(data)
    mpl, plt, sns = _libraries()
    with mpl.rc_context({'font.family': 'DejaVu Sans', 'axes.unicode_minus': False}):
        fig, ax = plt.subplots(figsize=(10, 5.4), layout='constrained')
        sns.histplot(x=data.frame['D_combined'], bins=edges, stat=stat, kde=False,
                     color='#287D8E', edgecolor='white', ax=ax)
        ax.axvline(description['baseline_D'], color='#C34B37', linewidth=2.5,
                   label=f"Bộ 30 đã chọn: D = {description['baseline_D']:.6f}")
        low = min(description['baseline_D'], description['random_min_D'])
        high = max(description['baseline_D'], description['random_max_D'])
        ax.set_xlim(max(0, low - bin_width), min(1, high + bin_width))
        ax.set(xlabel='D — sai lệch cơ cấu chiều dài RC (thấp hơn là gần mạng hơn)',
               ylabel='Tỷ lệ bộ ngẫu nhiên (%)' if stat == 'percent' else 'Số bộ ngẫu nhiên',
               title=f"Phân bố D của {len(data.frame):,} bộ 30 ngẫu nhiên theo quota")
        ax.legend(loc='upper right')
        fig.supxlabel(f"D không lớn hơn bộ gốc: {description['no_higher_D_count']}/{len(data.frame)} bộ. "
                      f"Khoảng D rộng {bin_width:g}; đây là khoảng trình bày, không phải ngưỡng đạt.", fontsize=9)
        fig._lez_plot_settings = {'source': data.report['fingerprint'], 'kind': 'histogram',
                                  'bin_width': bin_width, 'stat': stat}
    return fig


def plot_d_relationship(data, x_metric='unique_rc_coverage_fraction', fit_line=True):
    result = regression_summary(data, x_metric)
    scale, xlabel, _ = X_METRICS[x_metric]
    mpl, plt, sns = _libraries()
    with mpl.rc_context({'font.family': 'DejaVu Sans', 'axes.unicode_minus': False}):
        fig, ax = plt.subplots(figsize=(10, 5.4), layout='constrained')
        sns.regplot(x=data.frame[x_metric].to_numpy() * scale, y=data.frame['D_combined'],
                    fit_reg=fit_line and result['status'] == 'fitted', ci=None, truncate=True,
                    scatter_kws={'s': 18, 'alpha': .30, 'color': '#287D8E'},
                    line_kws={'color': '#174C64', 'linewidth': 2}, ax=ax)
        # The baseline is a reference point, never a training observation.
        ax.scatter([result['baseline_x']], [result['baseline_D']], marker='*', s=250,
                   color='#C34B37', edgecolors='white', linewidths=.7, zorder=5, label='Bộ 30 đã chọn')
        ax.set(xlabel=xlabel, ylabel='D — sai lệch cơ cấu chiều dài RC',
               title='Quan hệ giữa chỉ tiêu của bộ tuyến và D trên các bộ ngẫu nhiên')
        ax.legend(loc='best')
        r2 = result['r_squared']
        note = (f"Hồi quy mô tả chỉ dùng {len(data.frame):,} bộ ngẫu nhiên; "
                + (f"R² = {r2:.3f}. " if fit_line and r2 is not None else '')
                + 'Không diễn giải là quan hệ nhân quả hoặc kiểm chứng thực địa.')
        fig.supxlabel(note, fontsize=9)
        fig._lez_plot_settings = {'source': data.report['fingerprint'], 'kind': 'relationship',
                                  'x_metric': x_metric, 'fit_line': fit_line}
    return fig


def export_comparison(data, histogram, relationship, *, bin_width=0.02,
                      stat='percent', x_metric='unique_rc_coverage_fraction', fit_line=True,
                      output_root=None):
    """Write plots/tables separately from immutable inputs, with provenance."""
    for name, expected in data.input_hashes.items():
        if file_hash(input_path(data.work, name)) != expected:
            raise ValueError('Nguồn đổi sau khi đọc; chạy lại từ cell đọc dữ liệu: ' + name)
    expected_histogram = {'source': data.report['fingerprint'], 'kind': 'histogram',
                          'bin_width': bin_width, 'stat': stat}
    expected_relationship = {'source': data.report['fingerprint'], 'kind': 'relationship',
                             'x_metric': x_metric, 'fit_line': fit_line}
    if (getattr(histogram, '_lez_plot_settings', None) != expected_histogram
            or getattr(relationship, '_lez_plot_settings', None) != expected_relationship):
        raise ValueError('Đã đổi tham số hoặc nguồn: vẽ lại cả hai hình trước khi xuất.')
    intervals = d_interval_table(data, bin_width)
    regression = regression_summary(data, x_metric)
    settings = {'bin_width': bin_width, 'histogram_stat': stat, 'x_metric': x_metric,
                'fit_line': fit_line, 'regression_ci': None}
    import matplotlib
    import seaborn
    runtime = {'numpy': np.__version__, 'pandas': pd.__version__,
               'matplotlib': matplotlib.__version__, 'seaborn': seaborn.__version__}
    fingerprint = digest({'inputs': data.input_hashes, 'source': data.source,
                          'settings': settings, 'code': file_hash(__file__), 'runtime': runtime})
    root = Path(output_root).resolve() if output_root else data.work / 'reports/selection/plots'
    root = root.resolve()
    if root == data.work or root.is_relative_to(data.work / 'data') or root.is_relative_to(data.work / 'docs'):
        raise ValueError('Đầu ra phải tách khỏi dữ liệu/bản kết quả nguồn; dùng reports/selection/plots.')
    directory = root / fingerprint[:20]
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, figure in (('D_histogram', histogram), ('D_relationship', relationship)):
        for extension in ('png', 'svg'):
            path = directory / (name + '.' + extension)
            buffer = BytesIO()
            with matplotlib.rc_context({'svg.fonttype': 'none', 'font.family': 'DejaVu Sans'}):
                figure.savefig(buffer, format=extension, dpi=240, bbox_inches='tight')
            atomic_bytes(path, buffer.getvalue())
            outputs.append(path)
    rows = intervals.to_dict(orient='records')
    write_csv(directory / 'D_intervals.csv', rows, list(intervals.columns))
    report = {'status': 'completed_descriptive_plots', 'created_at': now(), 'fingerprint': fingerprint,
              'source': data.source, 'source_run_fingerprint': data.report['fingerprint'],
              'source_finished_at': data.report.get('finished_at'), 'settings': settings,
              'source_reviewed_on': data.report.get('reviewed_on'),
              'comparison': describe_comparison(data), 'regression': regression,
              'runtime': runtime, 'input_hashes': data.input_hashes,
              'random_sampling_rerun': False, 'baseline_selection_modified': False,
              'network_calls': 0, 'qgis_started': False,
              'measurement_verified': False,
              'osm_attribution': '© OpenStreetMap contributors; ODbL-1.0',
              'paths': {p.stem + '_' + p.suffix[1:]: relative(p, data.work) for p in outputs}}
    atomic_json(directory / 'plot_report.json', report)
    outputs += [directory / 'D_intervals.csv', directory / 'plot_report.json']
    atomic_json(directory / 'manifest.json', {'complete': True, 'fingerprint': fingerprint,
                'output_hashes': {p.name: file_hash(p) for p in outputs}})
    return directory, report
