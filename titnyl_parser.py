import math
from typing import List, Tuple, Optional, Any
import pyproj
import numpy as np
from scipy.interpolate import UnivariateSpline
from scipy.ndimage import gaussian_filter1d

# Klasse for å lagre ett TIT-element (linje, bue eller klotoide)
class TitElement:
    def __init__(self, 
                 start_station: float, 
                 start_radius: float, 
                 end_radius: float, 
                 start_n: float, 
                 start_e: float, 
                 end_n: float, 
                 end_e: float, 
                 end_station: float):
        self.start_station = start_station
        self.end_station = end_station
        self.start_radius = start_radius
        self.end_radius = end_radius
        self.start_n = start_n
        self.start_e = start_e
        self.end_n = end_n
        self.end_e = end_e

# Automatisk deteksjon av EPSG-kode fra koordinater
def detect_epsg(val1: float, val2: float) -> Tuple[Optional[str], bool]:    
    LAT_MIN, LAT_MAX = 57.0, 72.0
    LON_MIN, LON_MAX = 4.0, 32.0

    target_crs = pyproj.CRS("EPSG:4326")

    # Kandidater for EPSG (UTM og NTM)
    candidates = ["25832", "25833", "25834", "25835", "25831"]
    candidates.extend([str(5100 + i) for i in range(5, 31)])
    candidates.append("5973")  # NTM13 (EPSG:5973)
    configurations = [
        (val1, val2, False), 
        (val2, val1, True) 
    ]

    for n_curr, e_curr, is_swap in configurations:
        if e_curr > 200000:
             check_list = candidates[:5] + candidates[5:]
        else:
             check_list = candidates[5:] + candidates[:5]

        for epsg in check_list:
            try:
                source_crs = pyproj.CRS(f"EPSG:{epsg}")
                transformer = pyproj.Transformer.from_crs(source_crs, target_crs, always_xy=True)
                lon, lat = transformer.transform(e_curr, n_curr)
                
                if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                    return epsg, is_swap
            except Exception:
                continue
            
    return None, False

# Parser NYL-fil (vertikalprofil med stasjon og høyde)
def parse_nyl(content: str) -> List[Tuple[float, float]]:
    points = []
    lines = content.splitlines()
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        try:
            station = float(parts[0])
            z = float(parts[1])
            points.append((station, z))
        except ValueError:
            continue
            
    points.sort(key=lambda x: x[0])
    return points

# Parser TIT-fil (horisontalggeometri med linjer, buer og klotoider)
def parse_tit(content: str) -> List[TitElement]:
    elements = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line1 = lines[i].strip()
        if not line1:
            i += 1
            continue
            
        parts1 = line1.split()
        
        if len(parts1) < 6 or parts1[0] != '10':
            i += 1
            continue
            
        try:
            seq = float(parts1[1])
            start_station = float(parts1[2])
            start_radius = float(parts1[3])
            end_radius = float(parts1[4])
            a_param = float(parts1[5])
            
            if i + 1 >= len(lines):
                break
                
            l2 = lines[i+1].strip()
            if not l2.startswith('10'):
                i += 1
                continue
            
            if l2.find('10') == -1:
                i += 2
                continue
                        
            start_n_str = l2[2:13]
            start_e_str = l2[13:24]
            end_n_str   = l2[24:35]
            end_e_str   = l2[35:46]
            end_stat_str= l2[46:57]
            
            start_n = float(start_n_str)
            start_e = float(start_e_str)
            end_n = float(end_n_str)
            end_e = float(end_e_str)
            end_station = float(end_stat_str)
            
            elements.append(TitElement(
                start_station=start_station,
                start_radius=start_radius,
                end_radius=end_radius,
                start_n=start_n,
                start_e=start_e,
                end_n=end_n,
                end_e=end_e,
                end_station=end_station
            ))
            
            i += 2
        except (ValueError, IndexError):
            i += 1
            
    return elements

# Interpoler høyde fra NYL-punkter for gitt stasjon
def interpolate_z(station: float, z_points: List[Tuple[float, float]]) -> float:
    if not z_points:
        return 0.0
    
    if station <= z_points[0][0]:
        return z_points[0][1]
    if station >= z_points[-1][0]:
        return z_points[-1][1]
        
    for j in range(len(z_points) - 1):
        s1, z1 = z_points[j]
        s2, z2 = z_points[j+1]
        if s1 <= station <= s2:
            if s2 == s1: return z1
            ratio = (station - s1) / (s2 - s1)
            return z1 + ratio * (z2 - z1)
    return 0.0


def _safe_float(value: Any) -> float:
    """Try to coerce various numeric-like containers to a scalar float."""
    try:
        if isinstance(value, np.ndarray):
            if value.size == 0:
                return 0.0
            return float(value.astype(float, copy=False).ravel()[0])
        if isinstance(value, (list, tuple)):
            if not value:
                return 0.0
            return _safe_float(value[0])
        return float(value)
    except Exception:
        return 0.0


# Generer tette punkter langs geometrien (smooth kurver)
def generate_geometry(elements: List[TitElement], z_points: List[Tuple[float, float]], step: float = 5.0, smooth_z: bool = False) -> List[List[float]]:
    geometry_points = []
    all_z_values = []
    
    # Lag interpolator for z-verdier hvis smooth_z er aktivert
    z_interpolator = None
    if smooth_z and len(z_points) >= 2:
        try:
            # Slå sammen duplikate stasjoner ved å snitte z-verdier
            accum = {}
            for s, z in z_points:
                if s in accum:
                    acc_sum, acc_cnt = accum[s]
                    accum[s] = (acc_sum + z, acc_cnt + 1)
                else:
                    accum[s] = (z, 1)
            stations_nyl = sorted(accum.keys())
            z_nyl = [accum[s][0] / accum[s][1] for s in stations_nyl]

            if len(stations_nyl) >= 2:
                k_val = min(3, len(stations_nyl) - 1)
                # Interpolerende spline (s=0) og konstant ekstrapolering utenfor intervallet
                z_interpolator = UnivariateSpline(stations_nyl, z_nyl, k=k_val, s=0, ext=1)
        except Exception:
            z_interpolator = None
    
    # Behandle hvert geometrielement
    for el in elements:
        length = el.end_station - el.start_station
        if length <= 0.001:
            continue
        
        # Beregn krumning (k) fra radius
        k_start = -1.0 / el.start_radius if abs(el.start_radius) > 1e-4 else 0.0
        k_end = -1.0 / el.end_radius if abs(el.end_radius) > 1e-4 else 0.0
        
        num_steps = int(math.ceil(length / step))
        if num_steps < 2: num_steps = 2
        
        dk = k_end - k_start
        
        # Bygg lokal geometri med numerisk integrasjon
        curr_x, curr_y = 0.0, 0.0
        local_poly = [(0.0, 0.0)]
        ds = length / num_steps
        
        for i in range(1, num_steps + 1):
            s_prev = (i - 1) * ds
            s_curr = i * ds
            
            s_mid = (s_prev + s_curr) / 2.0
            theta_mid = k_start * s_mid + 0.5 * (dk / length) * s_mid * s_mid
            
            dx = math.cos(theta_mid) * ds
            dy = math.sin(theta_mid) * ds
            
            curr_x += dx
            curr_y += dy
            local_poly.append((curr_x, curr_y))
       
        # Roter og plasser geometrien i riktig posisjon
        target_dx = el.end_e - el.start_e
        target_dy = el.end_n - el.start_n
        
        local_end_angle = math.atan2(curr_y, curr_x)
        global_chord_angle = math.atan2(target_dy, target_dx)
        rotation = global_chord_angle - local_end_angle
        
        cos_rot = math.cos(rotation)
        sin_rot = math.sin(rotation)
        
        for i, (lx, ly) in enumerate(local_poly):
            rx = lx * cos_rot - ly * sin_rot
            ry = lx * sin_rot + ly * cos_rot
            final_e = el.start_e + rx
            final_n = el.start_n + ry
            
            s_val = el.start_station + (i * ds)
            
            # Bruk interpolerende spline hvis smooth_z er aktivert
            if z_interpolator is not None:
                try:
                    raw_z = z_interpolator(float(s_val))
                    z_val = _safe_float(raw_z)
                    if math.isnan(z_val):
                        z_val = interpolate_z(s_val, z_points)
                except Exception:
                    z_val = interpolate_z(s_val, z_points)
            else:
                z_val = interpolate_z(s_val, z_points)
            
            geometry_points.append([final_e, final_n, z_val])
            all_z_values.append(z_val)
    
    # Appliser gaussian smoothing til z-verdier hvis smooth_z er aktivert
    if smooth_z and len(all_z_values) > 1:
        try:
            # sigma skaleres svakt med antall punkter for å unngå oversmoothing
            sigma = max(1.0, min(5.0, len(all_z_values) / 500.0))
            smoothed_z = gaussian_filter1d(all_z_values, sigma=sigma)
            for i, point in enumerate(geometry_points):
                point[2] = float(smoothed_z[i])
        except Exception:
            pass  # Fallback til original verdier
            
    return geometry_points

# Hent kun endepunkter (forenklet geometri)
def extract_endpoints_only(elements: List[TitElement], z_points: List[Tuple[float, float]]) -> List[List[float]]:
    geometry_points = []
    if not elements:
        return []

    z_start = interpolate_z(elements[0].start_station, z_points)
    geometry_points.append([elements[0].start_e, elements[0].start_n, z_start])

    for i, el in enumerate(elements):
        z_end = interpolate_z(el.end_station, z_points)
        geometry_points.append([el.end_e, el.end_n, z_end])
        if i < len(elements) - 1:
            next_el = elements[i+1]
            if abs(next_el.start_e - el.end_e) > 0.01 or abs(next_el.start_n - el.end_n) > 0.01:
                z_next_start = interpolate_z(next_el.start_station, z_points)
                geometry_points.append([next_el.start_e, next_el.start_n, z_next_start])

    return geometry_points

# Transformer koordinater til WGS84 (lon, lat)
def transform_to_wgs84(points: List[List[float]], from_epsg: str) -> List[List[float]]:
    try:
        source_crs = pyproj.CRS(f"EPSG:{from_epsg}")
    except:
        source_crs = pyproj.CRS("EPSG:25832")
        
    target_crs = pyproj.CRS("EPSG:4326")
    transformer = pyproj.Transformer.from_crs(source_crs, target_crs, always_xy=True)
    
    transformed = []
    for p in points:
        e, n, z = p
        lon, lat = transformer.transform(e, n)
        transformed.append([lon, lat, z])
        
    return transformed

# Hovedfunksjon: konverter TIT og NYL til GeoJSON
def convert_tit_nyl_to_geojson(tit_content: str, nyl_content: str, epsg: str = "25832", filename: Optional[str] = None, smooth: bool = True, smooth_z: bool = False):
    tit_elements = parse_tit(tit_content)
    nyl_points = parse_nyl(nyl_content)
    
    # Håndter auto-deteksjon av EPSG
    final_epsg = epsg
    if epsg == "auto" and tit_elements:
        sample_n = tit_elements[0].start_n
        sample_e = tit_elements[0].start_e
        
        detected_epsg, swap_needed = detect_epsg(sample_n, sample_e)
        
        if detected_epsg:
            final_epsg = detected_epsg
            if swap_needed:
                for el in tit_elements:
                    el.start_n, el.start_e = el.start_e, el.start_n
                    el.end_n, el.end_e = el.end_e, el.end_n
        else:
            final_epsg = "25832" 
    
    # Velg glatt kurve eller kun endepunkter
    if smooth:
        raw_points_3d = generate_geometry(tit_elements, nyl_points, step=5.0, smooth_z=smooth_z)
    else:
        raw_points_3d = extract_endpoints_only(tit_elements, nyl_points)
    
    geo_points = transform_to_wgs84(raw_points_3d, final_epsg)
    
    properties = {
        "source": "titnyl-api",
        "epsg": final_epsg,
        "smooth": smooth,
        "smooth_z": smooth_z
    }
    if filename:
        properties["filename"] = filename

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "LineString",
                    "coordinates": geo_points
                }
            }
        ]
    }
