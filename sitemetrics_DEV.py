import sys
import datetime

import arcpy
from collections import namedtuple
from arcgis.gis import GIS
from arcgis.features import FeatureSet, GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry
from arcgis.geometry.filters import intersects
from arcgis.features.manage_data import overlay_layers
from arcgis.features import find_locations
from arcgis.geometry import filters
import pandas as pd
import json
import time
from uuid import uuid4


# # Permanently changes the pandas settings
# pd.set_option('display.max_rows', None)
# pd.set_option('display.max_columns', None)
# pd.set_option('display.width', None)
# pd.set_option('display.max_colwidth', -1)

def mapParcelIDandRunIDFields(inParcels, inParcelsIDField):
    runID = str(uuid4())

    inParcelsJson = inParcels.JSON
    inParcelsJson = inParcelsJson.replace(inParcelsIDField, 'parcelid')
    inParcelsDict = json.loads(inParcelsJson)

    newFieldsList = [f for f in inParcelsDict['fields'] if 'parcelid' not in f['name']]
    parcelIDField = {
        "name": "parcelid",
        "type": "esriFieldTypeString",
        "alias": "parcelid",
        "length": 255
    }
    runIDField = {
        "name": "runid",
        "type": "esriFieldTypeString",
        "alias": "runid",
        "length": 255
    }
    newFieldsList.append(parcelIDField)
    newFieldsList.append(runIDField)
    inParcelsDict['fields'] = newFieldsList

    # add the runID value to all the features
    for f in inParcelsDict['features']:
        f['attributes']['runid'] = runID

    inParcels_api_fset = FeatureSet.from_dict(inParcelsDict)

    return inParcels_api_fset


def uploadFeaturesToGeoportalLyr(inParcels, inputParcelsLyr, idFieldName):
    # push the parcels to the parcels layer in geoportal
    inParcels_api_fset = mapParcelIDandRunIDFields(inParcels, idFieldName)
    # inParcels.save(r"G:\Users\JoseLuis\arcgis_scripts_enxco\site_metrics", "test.shp")

    inputParcelsLyr.delete_features(where="1=1")
    # When making large number (250+ records at once) of edits,
    # append should be used over edit_features to improve performance and ensure service stability.
    inputParcelsLyr.edit_features(adds=inParcels_api_fset)

    return inputParcelsLyr


def createInAndOutBuildableField(unionFLyr):
    union_fset = unionFLyr.query()
    union_features = union_fset.features

    fid_job_column = [col for col in union_features[0].fields if 'fid_j' in col][0]

    for fd in union_features:
        if fd.attributes[fid_job_column] < 1:
            fd.attributes['parcel_bld_id'] = fd.attributes['parcelid'] + '_0'
        else:
            fd.attributes['parcel_bld_id'] = fd.attributes['parcelid'] + '_1'

    unionFLyr.edit_features(updates=union_features)

    return unionFLyr


try:
    inParcels = arcpy.GetParameter(0)

    # debug only  *****************************
    # inParcels = r"G:\Users\Ardy\GIS\APRX\scratch.gdb\test_polys_nozm"
    # inParcels = r"G:\Users\Ardy\GIS\APRX\scratch.gdb\test_parcels_FEMA"
    # inParcels = r"G:\Users\JoseLuis\arcgis_scripts_enxco\site_metrics\test_parcels_FEMA.shp"
    # inParcels = r"G:\Users\JoseLuis\arcgis_scripts_enxco\site_metrics\Default.gdb\test_parcels_FEMA_v2"
    # inParcels = r"G:\Projects\USA_West\Flores\05_GIS\053_Data\Parcels_Flores_CoreLogic_TojLoad_LPM_20221024.shp"
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tract_Tests_20221115\Desktop_Outputs.gdb\WI_Solar_v03_TractID14285_Tract'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tract_Tests_20221115\Desktop_Outputs.gdb\OK_GRDA_v01_TractID1323_Tract'

    # debug only end  *****************************

    # the BL_Source is always the Solar national

    # Buildable Land # FEMA 100 Year Floodplain  # 500 Year Floodplain
    # BL_Source      # F100_Acres                # F500_Acres
    # BL_Acres       # F100_Pcnt                 # F500_Pcnt
    # BL_Pcnt        # F100_BL_Acres             # F500_BL_Acres
    # F100_BL_Pcnt              # F500_BL_Pcnt

    # Slope(raster)      # Forested Land(raster)  # Bedrock - Shallow   # Bedrock - MidDepth(101 to 300 cm)
    # Slp10_Acres        # Forest_Acres           # BdRckSh_Acres       # BdRckMD_Acres
    # Slp10_Pcnt         # Forest_Pcnt            # BdRckSh_Pcnt        # BdRckMD_Pcnt
    # Slp10_BL_Acres     # Forest_BL_Acres        # BdRckSh_BL_Acres    # BdRckMD_BL_Acres
    # Slp10_BL_Pcnt      # Forest_BL_Pcnt         # BdRckSh_BL_Pcnt     # BdRckMD_BL_Pcnt

    rasterParams = namedtuple("rasterParams", "name id field")
    raster_inputs = [
        rasterParams('Forests_Only_From_LANDFIRE', 'ab97639707a846df87f7a2b6f4a91704', 'Forest'),
        rasterParams('Slope_over10perc_ned2usa_60m', '7136a66ef63148f69f2bf963a0778ce9', 'Slp10'),
        rasterParams('Soil_Bedrock_Depth_1_to_100cm_rc1_nogaps', '58d9638faa9f48f681e286cab4218402', 'BdRckSh'),
        rasterParams('Soil_Bedrock_Depth_101_to_300cm_rc1_nogaps', 'b13310e293b844c3a18c56d1712d8f2c', 'BdRckMD')
    ]
    vectorParams = namedtuple("vectorParams", "name id field whereClause")
    vector_inputs = [
        vectorParams("FEMA Flood Hazard Areas", '1db6910429d14a60bebae24cc87648d5', 'F100',
                     "FLD_ZONE in ('A', 'A99', 'AE', 'AH', 'AO')"),
        vectorParams("FEMA Flood Hazard Areas", '1db6910429d14a60bebae24cc87648d5', 'F500', "FLD_ZONE in ('X')")
    ]

    # inParcels = arcpy.FeatureSet(inParcels)
    # in case the OBJECTIDs are not starting at 1
    fc = arcpy.CopyFeatures_management(inParcels, 'in_memory/fc')
    inParcels = arcpy.FeatureSet(fc)

    # converting the inParcels featureset to a spatial dataframe. We will join the stats to parcelsSDF
    arcpy.CopyFeatures_management(inParcels, 'memory/tmp1')
    parcelsSDF = pd.DataFrame.spatial.from_featureclass('memory/tmp1')
    arcpy.Delete_management('memory/tmp1')

    # main fields for identify parcels
    ID_FIELD_PARCELS_SDF = 'OBJECTID'
    ID_FIELD_PARCELS_GEOPORTAL = 'parcelid'
    ID_FIELD_BLD_PARCELS_GEOPORTAL = 'parcel_bld_id'

    if type(parcelsSDF[ID_FIELD_PARCELS_SDF]) == 'Str':
        parcelsSDF[ID_FIELD_PARCELS_SDF] = parcelsSDF[ID_FIELD_PARCELS_SDF].astype('int')

    parcelsBuildableUnionLayerName = "sitemetrics_parcels_buildable_union_DEV"

    # the stats for each parcel are for the total of the parcel and for the buildable part of the parcel
    # prepare the input parcels and intersect with the buildable land
    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")

    arcpy.AddMessage("Fetching geoportal solar buildable land and holder for parcels")
    t0 = time.time()
    # find the solar national buildable land layer (National Solar Buildable Land)
    buildableItem = gis.content.get('21d180c3e40847a69c32cec4166fbeca')
    buildableLyr = buildableItem.layers[0]

    # find the site metric parcels layer (site_metrics_inputParcels)
    inputParcelsItem = gis.content.get('c52edce5c4324efea8383604903918ab')
    inputParcelsLyr = inputParcelsItem.layers[0]
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    inParcelsDesc = arcpy.Describe(inParcels)
    inParcelsExtent = inParcelsDesc.extent
    # creating context object and send to image server
    context = {"extent": {"xmin": inParcelsExtent.XMin,
                          "ymin": inParcelsExtent.YMin,
                          "xmax": inParcelsExtent.XMax,
                          "ymax": inParcelsExtent.YMax,
                          "spatialReference": {"wkid": inParcelsDesc.spatialReference.factoryCode}},
               "overwrite": True
               }

    # Intersect buildable and parcels in geoportal
    arcpy.AddMessage("Deleting old parcels in the geoportal layer ")
    t0 = time.time()
    inputParcelsLyr.delete_features(where="1 = 1")
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    arcpy.AddMessage("Uploading parcels to geoportal")
    t0 = time.time()
    inputParcelsLyr = uploadFeaturesToGeoportalLyr(inParcels, inputParcelsLyr, ID_FIELD_PARCELS_SDF)
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # intersecting buildable lands polys into a (new or preexisting) geoportal layer
    # https://developers.arcgis.com/python/api-reference/arcgis.features.find_locations.html
    try:
        parcel_bld_item = gis.content.search('tmpParcelSolar_DEV', 'feature layer')[0]  # tmpParcelSolar
        parcel_bld_item.delete()
    except Exception as e:
        arcpy.AddMessage('tmpParcelSolar_DEV does not exist yet')

    arcpy.AddMessage("Selecting intersecting buildable features into a new geoportal layer")
    t0 = time.time()
    # 00:00:58.45 seconds - intersect find_locations
    # find_locations - derive_new_locations returns partial feature records vs find_existing_locations was returning a much larger area
    # selected_buildable_layer = find_locations.derive_new_locations(input_layers=[buildableLyr, inputParcelsLyr],
    #                                                                expressions=[{"operator": "and", "layer": 0,
    #                                                                              "spatialRel": "intersects",
    #                                                                              "selectingLayer": 1}],
    #                                                                output_name='tmpParcelSolar', context=context)

    # 00:00:58.528 - withinDistance 0.1 feet find_locations
    selected_buildable_layer = find_locations.derive_new_locations(input_layers=[buildableLyr, inputParcelsLyr],
                                                                   expressions=[{"operator": "and",
                                                                                 "layer": 0,
                                                                                 "spatialRel": "withinDistance",
                                                                                 "selectingLayer": 1,
                                                                                 "distance": 0.001,
                                                                                 "units": "feet"}],
                                                                   output_name='tmpParcelSolar_DEV', context=context)
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # gis.content.search is for name specific & gis.content.get is for item id specific
    try:
        parcels_item = gis.content.search(parcelsBuildableUnionLayerName, 'feature layer')[0]  # sitemetrics_parcels_buildable_union
        parcels_item.delete()
    except Exception as e:
        arcpy.AddMessage('sitemetrics_parcels_buildable_union_DEV does not exist yet')

    arcpy.AddMessage("Unionising parcels with solar national buildable land")
    t0 = time.time()
    unionItem = overlay_layers(inputParcelsLyr, selected_buildable_layer, overlay_type='Union',
                               output_name=parcelsBuildableUnionLayerName, context=context)
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    unionFLyr = unionItem.layers[0]

    arcpy.AddMessage("Removing buildable land outside the parcels")
    t0 = time.time()
    # remove any parcels outside of union EXAMPLE: "parcelid = -1"
    unionFLyr.delete_features(where="parcelid = ''")
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # modify parcelid If fid_feature_set  is -1 then parcelid = parcelid_0 otherwise parcelid  = parcelid_1)
    # add new parcelid field for identifying within buildable (parcel_bld_id)
    parcel_bld_def = {'name': 'parcel_bld_id',
                      'type': 'esriFieldTypeString',
                      'alias': 'parcel_bld_id',
                      'domain': None,
                      'editable': True,
                      'nullable': True,
                      'sqlType': 'sqlTypeVarchar',
                      'length': 255}

    unionFLyr.manager.add_to_definition({'fields': [parcel_bld_def]})

    unionFLyr = createInAndOutBuildableField(unionFLyr)

    # get the current run ids. do we really need this?
    tmp_parcel_df = unionFLyr.query().sdf
    tmp_run_id = tmp_parcel_df['runid'][0]

    df_list = []
    # summarize area by parcelid and then by parcel_bld_id
    parcelBuildableAcres = tmp_parcel_df.groupby([ID_FIELD_PARCELS_GEOPORTAL]).analysisarea.sum()
    parcelBuildableAcres = parcelBuildableAcres.to_frame()
    parcelBuildableAcres.rename(columns={"analysisarea": "Acres"}, inplace=True)
    # convert sq miles to acres
    parcelBuildableAcres['Acres'] = parcelBuildableAcres['Acres'].multiply(640)
    df_list.append(parcelBuildableAcres)

    # summarize area by parcelsBuildableUnionIDField
    summarize_df = tmp_parcel_df.groupby([ID_FIELD_PARCELS_GEOPORTAL, ID_FIELD_BLD_PARCELS_GEOPORTAL]).analysisarea.sum().reset_index()
    summarize_df['analysisarea'] = summarize_df['analysisarea'].multiply(640)

    # pivot table to convert parcelsBuildableUnionIDField to parcelid
    summarize_df['buildableIndex'] = summarize_df[ID_FIELD_BLD_PARCELS_GEOPORTAL].str[-1:]
    tmp_pivot_table = summarize_df.pivot_table(index=ID_FIELD_PARCELS_GEOPORTAL, columns='buildableIndex',
                                               values='analysisarea')
    tmp_pivot_table.reset_index(inplace=True)
    tmp_pivot_table.rename(
        columns={'0': 'outBldAcres',
                 '1': 'inBldAcres'},
        inplace=True)
    df_list.append(tmp_pivot_table)

    # Make gp service calls asynchronously
    rasterToolbox = 'https://geoportal.edf-re.com/raggp/services;Other/getAcresAndPercRaster_DEV;token={};{}'.format(
        gis._con.token, gis.url)
    vectorToolbox = 'https://geoportal.edf-re.com/raggp/services;Other/getAcresAndPercVector_DEV;token={};{}'.format(
        gis._con.token, gis.url)
    arcpy.ImportToolbox(rasterToolbox)
    arcpy.ImportToolbox(vectorToolbox)

    arcpy.AddMessage("Making Raster Calls")
    t0 = time.time()
    resultList = []
    # Make raster calls
    for tmp_raster in raster_inputs:
        tmp_raster_result = arcpy.getAcresAndPercRasterDEV.getAcresAndPercRasterDEV(parcelsBuildableUnionLayerName,
                                                                                    tmp_run_id,
                                                                                    ID_FIELD_PARCELS_GEOPORTAL,
                                                                                    ID_FIELD_BLD_PARCELS_GEOPORTAL,
                                                                                    'Area in Square Miles',
                                                                                    tmp_raster.id,
                                                                                    tmp_raster.field)
        resultList.append(tmp_raster_result)

    arcpy.AddMessage("Making Vector Calls")
    # Make vector calls
    for tmp_vector in vector_inputs:
        tmp_vector_result = arcpy.getAcresAndPercVectorDEV.getAcresAndPercVectorDEV(unionItem.id,
                                                                                    tmp_run_id,
                                                                                    ID_FIELD_PARCELS_GEOPORTAL,
                                                                                    ID_FIELD_BLD_PARCELS_GEOPORTAL,
                                                                                    tmp_vector.id, tmp_vector.field,
                                                                                    tmp_vector.whereClause)
        resultList.append(tmp_vector_result)

    # Wait for all the calls to be processed
    waitTimeStart = time.time()
    for tmp_result in resultList:
        while tmp_result.status < 4:
            time.sleep(0.2)
            waitTime = time.time() - waitTimeStart
            if waitTime > 120:
                arcpy.AddMessage(f"Error: map service not responding. {tmp_result}")
                sys.exit()

    # This is added to get the resultOutputs from our gp results list to a record set
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    t0 = time.time()
    # store all the results in a list with dataframes
    arcpy.AddMessage("Cleaning stats tables")
    for result in resultList:
        d = json.loads(result.getOutput(0).JSON)  # response from gp calls as JSON
        df = pd.json_normalize(d, record_path=['features'])  # dataframe created from JSON
        # remove the attributes. prefix and the OBJECTID attribute
        df.columns = df.columns.str.lstrip('attributes.')
        df = df.drop(['OBJECTID'], axis=1, errors='ignore')
        df_list.append(df)

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # join all the stats tables
    t0 = time.time()

    arcpy.AddMessage("Joining stats tables")
    final_stats_table_merge = df_list[0]
    for df_i in df_list[1:]:
        final_stats_table_merge = final_stats_table_merge.merge(df_i, on=ID_FIELD_PARCELS_GEOPORTAL, how='outer')

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # join the final statists table with the input parcels
    t0 = time.time()

    arcpy.AddMessage("Joining stats tables to geometries")
    final_stats_table_merge[ID_FIELD_PARCELS_GEOPORTAL] = final_stats_table_merge[ID_FIELD_PARCELS_GEOPORTAL].astype(
        'int')
    parcelsWithStatsSDF = parcelsSDF.merge(final_stats_table_merge, left_on=ID_FIELD_PARCELS_SDF,
                                           right_on=ID_FIELD_PARCELS_GEOPORTAL)

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # return the statistics recordset
    t0 = time.time()

    arcpy.AddMessage("Creating final record set")
    inParcelsWithStats_arcpyfset = arcpy.FeatureSet()
    # This line is where the fail case happens of 'DataFrame' object has no attribute 'dtype'
    # Pandas says this error occurs because Series is a dtype and DataFrame has dtypes
    # https://github.com/Esri/arcgis-python-api/issues/1193 -- Similar to this error but no result
    inParcelsWithStats_arcgisfset = parcelsWithStatsSDF.spatial.to_featureset()
    inParcelsWithStats_arcpyfset.load(inParcelsWithStats_arcgisfset)
    arcpy.SetParameter(1, inParcelsWithStats_arcpyfset)

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    textResponse = f"### SITE METRICS COMPLETED SUCCESSFULLY BECAUSE I ROCK ###"
    arcpy.AddMessage(textResponse)
    arcpy.SetParameterAsText(2, textResponse)

except arcpy.ExecuteError:
    arcpy.AddMessage('-1-')
    arcpy.AddMessage(arcpy.GetMessages(1))
    arcpy.AddMessage('-2-')
    arcpy.AddMessage(arcpy.GetMessages(2))
    arcpy.AddError('-1-')
    arcpy.AddError(arcpy.GetMessages(1))
    arcpy.AddError('-2-')
    arcpy.AddError(arcpy.GetMessages(2))
except Exception as e:
    arcpy.AddMessage(e)
    arcpy.AddError(e)
