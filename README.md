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
for hver steg:
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

## Z-koordinat interpolasjon

NYL-filer inneholder vertikalprofil som `(stasjon, z_verdi)` par.

For en gitt stasjon `s` brukes lineær interpolasjon:

```
z(s) = z₁ + (s - s₁)/(s₂ - s₁) × (z₂ - z₁)
```

hvor `s₁ ≤ s ≤ s₂` er nærmeste punkter i NYL-data.

## Koordinattransformasjon

### EPSG-deteksjon

For å automatisk detektere koordinatsystem:

1. Test både (val1=N, val2=E) og (val1=E, val2=N)
2. For hver permutasjon, test kandidat-EPSG koder:
   - UTM-soner: 25831-25835
   - NTM-soner: 5105-5130
3. Transformer til WGS84 (EPSG:4326)
4. Sjekk om resultat er innenfor Norges grenser:
   - Latitude: 57.0°N - 72.0°N
   - Longitude: 4.0°E - 32.0°E

### WGS84-transformasjon

Bruker pyproj for korrekt kartprojeksjon:

```python
transformer = pyproj.Transformer.from_crs(
    source_crs="EPSG:25832",  # eller detektert EPSG
    target_crs="EPSG:4326",    # WGS84
    always_xy=True
)
lon, lat = transformer.transform(easting, northing)
```


