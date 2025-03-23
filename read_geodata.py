import geopandas as gpd
import requests
import pandas as pd
from shapely.validation import make_valid
from shapely.geometry import MultiPolygon, GeometryCollection
import folium
import io
import numpy as np
from branca.colormap import LinearColormap

# Function to convert GeometryCollection to MultiPolygon
def to_multipolygon(geom):
    if isinstance(geom, GeometryCollection):
        polygons = [g for g in geom.geoms if g.geom_type in ['Polygon', 'MultiPolygon']]
        if polygons:
            return MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
        return None
    return geom

# Function to truncate long text
def truncate_text(text, max_length=50):
    if isinstance(text, str) and len(text) > max_length:
        return text[:max_length] + "..."
    return text

print("Starting script execution...")

# ====== Read the Utah Elk Habitat data
try:
    elk_habitat_url = ("https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/Utah_Elk_Habitat/"
                       "FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson")
    elk_habitat_gdf = gpd.read_file(elk_habitat_url)
    elk_habitat_gdf = elk_habitat_gdf[elk_habitat_gdf.geometry.notna() & elk_habitat_gdf.geometry.is_valid]
    print(f"Elk habitat data loaded. Features: {len(elk_habitat_gdf)}")
except Exception as e:
    print(f"Error loading elk habitat data: {e}")
    exit()

# ====== Step 1: Get BOUNDARY_ID from FeatureServer/2 for HUNT_NBR='EB1007'
try:
    url_step1 = ("https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/Utah_Big_Game_Hunt_Boundaries_2025/"
                 "FeatureServer/2/query?outFields=*&where=HUNT_NBR%3D'EB1007'&f=geojson")
    response_step1 = requests.get(url_step1)
    if response_step1.status_code != 200:
        raise Exception(f"Failed to fetch URL. Status code: {response_step1.status_code}")
    gdf_step1 = gpd.read_file(io.StringIO(response_step1.text))
    boundary_ids = gdf_step1['BOUNDARY_ID'].unique().tolist()
    print(f"Step 1 completed. Boundary IDs: {boundary_ids}")
except Exception as e:
    print(f"Error in Step 1: {e}")
    exit()

if not boundary_ids:
    print("Error: No BOUNDARY_IDs found for EB1007. Cannot proceed.")
    exit()

# ====== Step 2: Use BOUNDARY_IDs to get geometry from FeatureServer/0
try:
    url_step2 = ("https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/Utah_Big_Game_Hunt_Boundaries_2025/"
                 "FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson")
    where_clause = "BoundaryID IN (" + ",".join(f"'{id}'" for id in boundary_ids) + ")"
    filtered_url_step2 = url_step2.replace("where=1%3D1", f"where={where_clause.replace(' ', '%20')}")
    response_step2 = requests.get(filtered_url_step2)
    if response_step2.status_code != 200:
        raise Exception(f"Failed to fetch URL. Status code: {response_step2.status_code}")
    gdf = gpd.read_file(io.StringIO(response_step2.text))
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]
    print(f"Step 2 completed. Features in gdf: {len(gdf)}")
except Exception as e:
    print(f"Error in Step 2: {e}")
    exit()

if gdf.empty:
    print("Error: gdf (EB1007) is empty after filtering. Cannot proceed.")
    exit()

# ====== Add Elk Population Data (Placeholder)
try:
    elk_data = pd.DataFrame({
        'BoundaryID': gdf['BoundaryID'],
        'Herd_Size': np.random.randint(500, 5000, size=len(gdf)),
        'Population_Density': np.random.uniform(0.5, 5.0, size=len(gdf)),
        'Management_Objective': np.random.randint(400, 4500, size=len(gdf))
    })
    gdf = gdf.merge(elk_data, on='BoundaryID', how='left')
    print("Elk population data added.")
except Exception as e:
    print(f"Error adding elk data: {e}")
    exit()

# ====== Clip elk_habitat_gdf to gdf (EB1007 boundary)
try:
    elk_habitat_in_gdf = gpd.clip(elk_habitat_gdf, gdf)
    print(f"Elk habitat clipped. Features: {len(elk_habitat_in_gdf)}")
except Exception as e:
    print(f"Error clipping elk habitat: {e}")
    exit()

# ====== Load Utah county boundaries and filter intersecting counties
try:
    counties_url = ("https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/UtahCountyBoundaries/"
                    "FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson")
    counties_gdf = gpd.read_file(counties_url)
    if gdf.crs != counties_gdf.crs:
        counties_gdf = counties_gdf.to_crs(gdf.crs)
    gdf_union = gdf.union_all()
    intersecting_counties_gdf = counties_gdf[counties_gdf.intersects(gdf_union)]
    intersecting_counties = intersecting_counties_gdf['NAME'].unique().tolist()
    print(f"Intersecting counties: {intersecting_counties}")
except Exception as e:
    print(f"Error loading counties: {e}")
    exit()

# ====== Construct and read parcel data
prefix = "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_"
suffix = "/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson"
valid_services = [f"{prefix}{county.replace(' ', '')}{suffix}" for county in intersecting_counties]
parcel_gdfs = []
max_record_count = 2000

try:
    for service_url in valid_services:
        offset = 0
        while True:
            paginated_url = f"{service_url}&resultOffset={offset}&resultRecordCount={max_record_count}"
            parcel_gdf = gpd.read_file(paginated_url)
            if not parcel_gdf.empty:
                parcel_gdf = parcel_gdf[parcel_gdf['geometry'].notna()]
                parcel_gdf['geometry'] = parcel_gdf['geometry'].apply(lambda x: make_valid(x) if x is not None else x)
                parcel_gdfs.append(parcel_gdf)
                if len(parcel_gdf) < max_record_count:
                    break
                offset += max_record_count
            else:
                break
    print(f"Parcel data loaded. Total parcels: {sum(len(p) for p in parcel_gdfs)}")
except Exception as e:
    print(f"Error loading parcel data: {e}")

if parcel_gdfs:
    try:
        combined_parcels_gdf = gpd.GeoDataFrame(pd.concat(parcel_gdfs, ignore_index=True), crs=gdf.crs)
        combined_parcels_gdf = combined_parcels_gdf[combined_parcels_gdf['geometry'].notna()]
        combined_parcels_gdf['geometry'] = combined_parcels_gdf['geometry'].apply(lambda x: make_valid(x) if x is not None else x)
        public_parcels_gdf = combined_parcels_gdf[~combined_parcels_gdf['OWN_TYPE'].isin(['Private', 'Tribal'])]
        public_parcels_gdf = public_parcels_gdf[public_parcels_gdf.geometry.is_valid]
        parcels_in_gdf = gpd.clip(public_parcels_gdf, gdf)
        clipped_public_parcels_gdf = gpd.clip(parcels_in_gdf, elk_habitat_in_gdf)
        clipped_public_parcels_gdf['geometry'] = clipped_public_parcels_gdf['geometry'].apply(to_multipolygon)
        clipped_public_parcels_gdf = clipped_public_parcels_gdf[clipped_public_parcels_gdf['geometry'].notna()]
        print(f"Public parcels clipped. Features: {len(clipped_public_parcels_gdf)}")
    except Exception as e:
        print(f"Error processing parcels: {e}")

# ====== Create Folium map
try:
    map_center = [(gdf.total_bounds[1] + gdf.total_bounds[3]) / 2, (gdf.total_bounds[0] + gdf.total_bounds[2]) / 2]
    m = folium.Map(location=map_center, zoom_start=10, tiles="OpenStreetMap")

    # Create a color scale for population density
    colormap = LinearColormap(
        colors=['yellow', 'orange', 'red'],
        vmin=gdf['Population_Density'].min(),
        vmax=gdf['Population_Density'].max(),
        caption="Elk Population Density (elk/sq mile)"
    )

    # Add gdf with color scale based on population density
    gdf['Description'] = gdf['Description'].apply(truncate_text)
    folium.GeoJson(
        gdf,
        name="Hunt Boundary (EB1007)",
        style_function=lambda x: {
            "color": "red",
            "weight": 2,
            "fillColor": colormap(x['properties']['Population_Density']),
            "fillOpacity": 0.5
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["Boundary_Name", "Description", "Herd_Size", "Population_Density", "Management_Objective"],
            aliases=["Boundary Name", "Description", "Herd Size", "Pop Density (elk/sq mi)", "Mgmt Objective"]
        )
    ).add_to(m)

    # Add elk_habitat_in_gdf (green)
    folium.GeoJson(
        elk_habitat_in_gdf,
        name="Elk Habitat within EB1007",
        style_function=lambda x: {
            "color": "green",
            "weight": 2,
            "fillOpacity": 0
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["SEASON", "VALUE", "COMMENTS"],
            aliases=["Season", "Value", "Comments"]
        )
    ).add_to(m)

    # Add clipped_public_parcels_gdf (blue)
    if parcel_gdfs:
        folium.GeoJson(
            clipped_public_parcels_gdf,
            name="Public Parcels",
            style_function=lambda x: {
                "color": "blue",
                "weight": 1,
                "fillColor": "blue",
                "fillOpacity": 0.5
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["PARCEL_ID", "OWN_TYPE"],
                aliases=["Parcel ID", "Ownership Type"]
            )
        ).add_to(m)

    # Add colormap and layer control
    colormap.add_to(m)
    folium.LayerControl().add_to(m)

    # Save and display
    m.save("hunt_map.html")
    print("Interactive map saved as 'hunt_map.html'. Open it in a web browser.")
except Exception as e:
    print(f"Error creating map: {e}")