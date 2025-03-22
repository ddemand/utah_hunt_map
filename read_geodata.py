import geopandas as gpd
import requests
import pandas as pd
from shapely.validation import make_valid
from shapely.geometry import MultiPolygon, GeometryCollection  # Added these imports
import folium
import io


# Function to convert GeometryCollection to MultiPolygon
def to_multipolygon(geom):
    if isinstance(geom, GeometryCollection):
        polygons = [g for g in geom.geoms if g.geom_type in ['Polygon', 'MultiPolygon']]
        if polygons:
            return MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
        return None  # Drop if no polygons
    return geom


# ====== Read the Utah Elk Habitat data (primary boundary)
elk_habitat_url = ("https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/Utah_Elk_Habitat/"
                   "FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson")
elk_habitat_gdf = gpd.read_file(elk_habitat_url)
print(f"elk_habitat_gdf feature count: {len(elk_habitat_gdf)}")
print(f"elk_habitat_gdf CRS: {elk_habitat_gdf.crs}")
print(f"elk_habitat_gdf null geometries: {elk_habitat_gdf['geometry'].isna().sum()}")
print(
    f"elk_habitat_gdf invalid geometries: {len(elk_habitat_gdf[~elk_habitat_gdf.geometry.is_valid] if not elk_habitat_gdf.empty else 0)}")
print(f"elk_habitat_gdf bounds: {elk_habitat_gdf.total_bounds if not elk_habitat_gdf.empty else 'Empty'}")
print(f"elk_habitat_gdf columns: {elk_habitat_gdf.columns.tolist()}")

# Filter elk_habitat_gdf to valid, non-null geometries
elk_habitat_gdf = elk_habitat_gdf[elk_habitat_gdf.geometry.notna() & elk_habitat_gdf.geometry.is_valid]
print(f"elk_habitat_gdf feature count after filtering: {len(elk_habitat_gdf)}")
if elk_habitat_gdf.empty:
    print("elk_habitat_gdf is empty after filtering. Cannot proceed.")
    exit()

# ====== Step 1: Get BOUNDARY_ID from FeatureServer/2 for HUNT_NBR='EB1007'
url_step1 = ("https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/Utah_Big_Game_Hunt_Boundaries_2025/"
             "FeatureServer/2/query?outFields=*&where=HUNT_NBR%3D'EB1007'&f=geojson")
print(f"Fetching BOUNDARY_ID from: {url_step1}")
response_step1 = requests.get(url_step1)
if response_step1.status_code == 200:
    print(f"Raw response (first 200 chars): {response_step1.text[:200]}")
    try:
        gdf_step1 = gpd.read_file(io.StringIO(response_step1.text))
    except Exception as e:
        print(f"Pyogrio failed: {e}. Trying with fiona engine...")
        gdf_step1 = gpd.read_file(io.StringIO(response_step1.text), engine="fiona")
else:
    print(f"Failed to fetch URL. Status code: {response_step1.status_code}")
    gdf_step1 = gpd.GeoDataFrame()

print(f"gdf_step1 feature count: {len(gdf_step1)}")
print(f"gdf_step1 null geometries: {gdf_step1['geometry'].isna().sum() if not gdf_step1.empty else 'N/A'}")
print(f"gdf_step1 head:\n{gdf_step1.head().to_string() if not gdf_step1.empty else 'Empty'}")

# Extract unique BOUNDARY_IDs
if not gdf_step1.empty:
    boundary_ids = gdf_step1['BOUNDARY_ID'].unique().tolist()
    print(f"Unique BOUNDARY_IDs for EB1007: {boundary_ids}")
else:
    print("Error: No BOUNDARY_IDs found for EB1007 in FeatureServer/2. Cannot proceed.")
    exit()

# ====== Step 2: Use BOUNDARY_IDs to get geometry from FeatureServer/0
url_step2 = ("https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/Utah_Big_Game_Hunt_Boundaries_2025/"
             "FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson")
where_clause = "BoundaryID IN (" + ",".join(f"'{id}'" for id in boundary_ids) + ")"
filtered_url_step2 = url_step2.replace("where=1%3D1", f"where={where_clause.replace(' ', '%20')}")
print(f"Fetching EB1007 geometry from: {filtered_url_step2}")
response_step2 = requests.get(filtered_url_step2)
if response_step2.status_code == 200:
    print(f"Raw response (first 200 chars): {response_step2.text[:200]}")
    try:
        gdf = gpd.read_file(io.StringIO(response_step2.text))
    except Exception as e:
        print(f"Pyogrio failed: {e}. Trying with fiona engine...")
        gdf = gpd.read_file(io.StringIO(response_step2.text), engine="fiona")
else:
    print(f"Failed to fetch URL. Status code: {response_step2.status_code}")
    gdf = gpd.GeoDataFrame()

print(f"gdf feature count: {len(gdf)}")
print(f"gdf CRS: {gdf.crs if not gdf.empty else 'N/A'}")
print(f"gdf null geometries: {gdf['geometry'].isna().sum() if not gdf.empty else 'N/A'}")
print(f"gdf invalid geometries: {len(gdf[~gdf.geometry.is_valid]) if not gdf.empty else 'N/A'}")
print(f"gdf bounds: {gdf.total_bounds if not gdf.empty else 'Empty'}")
print(f"gdf head:\n{gdf.head().to_string() if not gdf.empty else 'Empty'}")

# Filter gdf to valid, non-null geometries
gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid] if not gdf.empty else gdf
print(f"gdf feature count after filtering: {len(gdf)}")
if gdf.empty:
    print("Error: gdf (EB1007) is empty after filtering. Cannot proceed without valid EB1007 boundary.")
    exit()

# ====== Clip elk_habitat_gdf to gdf (EB1007 boundary)
elk_habitat_in_gdf = gpd.clip(elk_habitat_gdf, gdf)
print(f"elk_habitat_in_gdf feature count: {len(elk_habitat_in_gdf)}")
print(f"elk_habitat_in_gdf bounds: {elk_habitat_in_gdf.total_bounds if not elk_habitat_in_gdf.empty else 'Empty'}")

# ====== Load Utah county boundaries
counties_url = ("https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/UtahCountyBoundaries/"
                "FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson")
counties_gdf = gpd.read_file(counties_url)
all_counties = counties_gdf['NAME'].unique().tolist()
print(f"All Utah Counties: {all_counties}")

# ====== Filter counties that intersect with gdf (EB1007)
if gdf.crs != counties_gdf.crs:
    counties_gdf = counties_gdf.to_crs(gdf.crs)
gdf_union = gdf.union_all()
intersecting_counties_gdf = counties_gdf[counties_gdf.intersects(gdf_union)]
intersecting_counties = intersecting_counties_gdf['NAME'].unique().tolist()
print(f"\nCounties intersecting with gdf (EB1007): {intersecting_counties}")

# ====== Construct parcel service URLs
prefix = "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_"
suffix = "/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson"
valid_services = [f"{prefix}{county.replace(' ', '')}{suffix}" for county in intersecting_counties]

# ====== Read all parcel data with pagination
parcel_gdfs = []
max_record_count = 2000

for service_url in valid_services:
    offset = 0
    while True:
        paginated_url = f"{service_url}&resultOffset={offset}&resultRecordCount={max_record_count}"
        print(f"Fetching records from: {paginated_url}")
        try:
            parcel_gdf = gpd.read_file(paginated_url)
            if not parcel_gdf.empty:
                parcel_gdf = parcel_gdf[parcel_gdf['geometry'].notna()]
                parcel_gdf['geometry'] = parcel_gdf['geometry'].apply(lambda x: make_valid(x) if x is not None else x)
                parcel_gdfs.append(parcel_gdf)
                print(f"Loaded {len(parcel_gdf)} features from offset {offset}")
                if len(parcel_gdf) < max_record_count:
                    break
                offset += max_record_count
            else:
                print("No features found at this offset.")
                break
        except Exception as e:
            print(f"Error loading {paginated_url}: {e}")
            break

# Combine all parcel GeoDataFrames into one
if parcel_gdfs:
    combined_parcels_gdf = gpd.GeoDataFrame(pd.concat(parcel_gdfs, ignore_index=True), crs=gdf.crs)
    combined_parcels_gdf = combined_parcels_gdf[combined_parcels_gdf['geometry'].notna()]
    combined_parcels_gdf['geometry'] = combined_parcels_gdf['geometry'].apply(
        lambda x: make_valid(x) if x is not None else x)

    print(f"\nTotal features in combined_parcels_gdf (before filtering): {len(combined_parcels_gdf)}")
    print("Unique OWN_TYPE values (before filtering):", combined_parcels_gdf['OWN_TYPE'].unique().tolist())

    # ====== Filter out Private and Tribal parcels
    public_parcels_gdf = combined_parcels_gdf[~combined_parcels_gdf['OWN_TYPE'].isin(['Private', 'Tribal'])]
    public_parcels_gdf = public_parcels_gdf[public_parcels_gdf.geometry.is_valid]
    print(f"Total features in public_parcels_gdf (after OWN_TYPE filtering): {len(public_parcels_gdf)}")
    print("Unique OWN_TYPE values (after filtering):", public_parcels_gdf['OWN_TYPE'].unique().tolist())

    # ====== Clip public_parcels_gdf to gdf and then to elk_habitat_in_gdf
    parcels_in_gdf = gpd.clip(public_parcels_gdf, gdf)
    print(f"Parcels within gdf (EB1007): {len(parcels_in_gdf)}")
    clipped_public_parcels_gdf = gpd.clip(parcels_in_gdf, elk_habitat_in_gdf)
    print(
        f"Final clipped_public_parcels_gdf (within EB1007 and elk habitat) before geometry fix: {len(clipped_public_parcels_gdf)}")

    # ====== Fix GeometryCollection to MultiPolygon
    clipped_public_parcels_gdf['geometry'] = clipped_public_parcels_gdf['geometry'].apply(to_multipolygon)
    clipped_public_parcels_gdf = clipped_public_parcels_gdf[
        clipped_public_parcels_gdf['geometry'].notna()]  # Drop any nulls from conversion
    print(
        f"Final clipped_public_parcels_gdf (within EB1007 and elk habitat) after geometry fix: {len(clipped_public_parcels_gdf)}")

    # ====== Create Folium map
    try:
        minx, miny, maxx, maxy = gdf.total_bounds
        map_center = [(miny + maxy) / 2, (minx + maxx) / 2]
    except ValueError:
        print("Warning: gdf bounds invalid. Defaulting to Utah center.")
        map_center = [39.5, -111.5]

    m = folium.Map(location=map_center, zoom_start=10, tiles="OpenStreetMap")

    # Add gdf (red)
    folium.GeoJson(
        gdf,
        name="Hunt Boundary (EB1007)",
        style_function=lambda x: {"color": "red", "weight": 2, "fillOpacity": 0},
        tooltip=folium.GeoJsonTooltip(fields=["Boundary_Name", "Description"], aliases=["Boundary Name", "Description"])
    ).add_to(m)

    # Add elk_habitat_in_gdf (green)
    folium.GeoJson(
        elk_habitat_in_gdf,
        name="Elk Habitat within EB1007",
        style_function=lambda x: {"color": "green", "weight": 2, "fillOpacity": 0},
        tooltip=folium.GeoJsonTooltip(fields=["SEASON", "VALUE", "COMMENTS"], aliases=["Season", "Value", "Comments"])
    ).add_to(m)

    # Add clipped_public_parcels_gdf (blue)
    folium.GeoJson(
        clipped_public_parcels_gdf,
        name="Public Parcels",
        style_function=lambda x: {"color": "blue", "weight": 1, "fillColor": "blue", "fillOpacity": 0.5},
        tooltip=folium.GeoJsonTooltip(fields=["PARCEL_ID", "OWN_TYPE"], aliases=["Parcel ID", "Ownership Type"])
    ).add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)

    # Save and display
    m.save("hunt_map.html")
    print("Interactive map saved as 'hunt_map.html'. Open it in a web browser.")

else:
    print("\nNo parcel data loaded from valid_services.")