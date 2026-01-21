# Dokumentasjon for TIT/NYL Parser

## Oversikt

Denne filen forklarer den matematiske teorien bak geometrigenerering fra VIPS/NovaPoint TIT-filer.

## TIT-filformat (Record Type 10)

TIT-filer inneholder horisontale veggeometrielementer med 2-linjers format:

**Linje 1:** `10 Seq StartStation StartRadius EndRadius A-param Unused`
**Linje 2:** `10 StartN StartE EndN EndE EndStation` (fast bredde, 11 tegn per kolonne)

### Elementtyper

Basert på radiusverdiene kan vi identifisere:
- **Rett linje:** StartRadius = 0, EndRadius = 0
- **Sirkulær kurve:** StartRadius = EndRadius ≠ 0
- **Klotoide/spiral:** StartRadius ≠ EndRadius

## Kurvatur og geometrigenerering

### Kurvaturfunksjon

For et veggeometri-element er kurvaturen `k(s)` som funksjon av stasjon `s`:

```
k(s) = k_start + (k_end - k_start) × (s / L)
```

hvor:
- `k_start = -1/R_start` (negativ pga. filkonvensjon: negativ radius = venstresvingk_end = -1/R_end`
- `L = lengde av elementet

### Vinkelintegrasjon

Retningsvinkelen θ(s) ved stasjon s fås ved å integrere kurvaturen:

```
θ(s) = ∫₀ˢ k(σ) dσ = k_start × s + ½ × (dk/dL) × s²
```

### Lokal geometri

I et lokalt koordinatsystem (startpunkt i origo, initiell retning langs x-aksen):

```
x(s) = ∫₀ˢ cos(θ(σ)) dσ
y(s) = ∫₀ˢ sin(θ(σ)) dσ
```

Vi bruker numerisk integrasjon (midtpunktsregel) med skritt `ds`:

```python
for hvert steg:
    s_mid = (s_prev + s_curr) / 2
    θ_mid = k_start × s_mid + ½ × (dk/L) × s_mid²
    dx = cos(θ_mid) × ds
    dy = sin(θ_mid) × ds
    x += dx
    y += dy
```

### Rotasjon til globalt system

Etter integrasjon har vi en lokal polyline fra (0,0) til (x_end, y_end).
Vi må rotere denne til å matche de globale koordinatene fra TIT-filen:

1. Beregn lokal sluttvinkel: `α_local = atan2(y_end, x_end)`
2. Beregn global kordvinkel: `α_global = atan2(EndN - StartN, EndE - StartE)`
3. Rotasjonsvinkel: `φ = α_global - α_local`

For hvert lokalt punkt (x_l, y_l):

```
x_rotert = x_l × cos(φ) - y_l × sin(φ)
y_rotert = x_l × sin(φ) + y_l × cos(φ)

E_global = StartE + x_rotert
N_global = StartN + y_rotert
```

## Z-koordinat interpolasjon og smoothing

NYL-filer inneholder vertikalprofil som `(stasjon, z_verdi)` par.

### Lineær interpolasjon (standard)

For en gitt stasjon `s` brukes lineær interpolasjon:

```
z(s) = z₁ + (s - s₁)/(s₂ - s₁) × (z₂ - z₁)
```

hvor `s₁ ≤ s ≤ s₂` er nærmeste punkter i NYL-data.

### Z-smoothing med parabolske vertikalkurver

Når `smooth_z=True` appliseres parabolske vertikalkurver rundt knekkpunkter (endringer i stigningstall):

**Algoritme:**

1. **Detektér knekkpunkter:** Finn punkter hvor stigningstallet endrer seg betydelig
   ```
   A = g₂ - g₁  (algebrisk differanse)
   ```

2. **Lag vertikalkurve:** For hvert knekkpunkt, interpoler en parabolsk kurve over lengde L (100m):
   ```
   z(x) = z_start + g₁·x + (A/(2L))·x²
   ```
   
   hvor:
   - `z_start` = z-verdi ved start av kurve
   - `g₁` = stigningstall før knekkpunkt (konstant)
   - `g₂` = stigningstall etter knekkpunkt (konstant)
   - `A = g₂ - g₁` = algebrisk differanse
   - `L` = kurvelengde (100m)
   - `x` = avstand fra start av kurve (0 til L)

3. **Tangering:** Kurven tangerer begge lineære deler:
   - Ved start: stigning = g₁
   - Ved slutt: stigning = g₂

4. **Resultat:** Realistisk vertikalkurvatur som bevarer lineære deler og smoothes kun rundt knekkpunktene

**Brukseksempel:**

```python
# Med z-smoothing (parabolske vertikalkurver)
result = convert_tit_nyl_to_geojson(
    tit_content, nyl_content,
    smooth=True,      # Smooth horisontal geometri
    smooth_z=True     # Smooth vertikal profil (parabolske kurver)
)
```

**Anvendelse:** Denne smoothingen er særlig nyttig for energimodeller av kjøretøyer, hvor realistisk vertikalkurvatur er viktig for å beregne akselerasjon og energiforbruk.

## Koordinattransformasjon

### EPSG-deteksjon

For å automatisk detektere koordinatsystem:

1. Test både (val1=N, val2=E) og (val1=E, val2=N)
2. For hver permutasjon, test kandidat-EPSG koder:
    - UTM-soner: 25831-25835
    - NTM-soner: 5105-5130 og 5973 (NTM13)
3. Transformer til WGS84 (EPSG:4326)
4. Sjekk om resultat er innenfor Norges grenser:
   - Latitude: 57.0°N - 72.0°N
   - Longitude: 4.0°E - 32.0°E


