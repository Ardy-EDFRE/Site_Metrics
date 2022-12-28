import sys
import os
import datetime
import numpy as np
import arcpy
from collections import namedtuple
from arcgis.gis import GIS
from arcgis.features import FeatureSet
# from arcgis.features import GeoAccessor, GeoSeriesAccessor
# from arcgis.geometry import Geometry
# from arcgis.geometry.filters import intersects
from arcgis.features.manage_data import overlay_layers
from arcgis.features import find_locations
import pandas as pd
import json
import time
from uuid import uuid4


# # Permanently changes the pandas settings
# pd.set_option('display.max_rows', None)
# pd.set_option('display.max_columns', None)
# pd.set_option('display.width', None)
# pd.set_option('display.max_colwidth', -1)


def getVoltageWhereClauses(minVolt, maxVolt):
    transWhereClause = ""
    subsWhereClause = ""

    if minVolt == '' and maxVolt == '':
        return 'noWhereClause', 'noWhereClause'

    if minVolt != '':
        if int(minVolt) > 0:
            transWhereClause = f'VOLTAGE_KV > {minVolt}'
            subsWhereClause = f'MX_VOLT_KV > {minVolt}'

    if maxVolt != '':
        if int(maxVolt) > 0:
            transWhereClause = f'VOLTAGE_KV < {maxVolt}'
            subsWhereClause = f'MX_VOLT_KV < {maxVolt}'

    if minVolt != '' and maxVolt != '':
        if int(minVolt) > 0 and int(maxVolt) > 0:
            transWhereClause = f'VOLTAGE_KV > {minVolt} AND VOLTAGE_KV < {maxVolt}'
            subsWhereClause = f'MX_VOLT_KV > {minVolt} AND MX_VOLT_KV < {maxVolt}'

    return transWhereClause, subsWhereClause


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


def createInAndOutBuildableField(unionFLyr, ID_FIELD_BLD_PARCELS_GEOPORTAL):
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

    # If the fid_feature_set field is -1 then parcelid = parcelid_0 otherwise parcelid = parcelid_1)
    unionBLDField = ''
    for fld in unionFLyr.properties.fields:
        if fld.name.startswith('fid_j'):
            unionBLDField = fld.name

    unionFLyr.calculate(where=f"{unionBLDField}<1",
                        calc_expression={"field": ID_FIELD_BLD_PARCELS_GEOPORTAL,
                                         "sqlExpression": "CONCAT(parcelid, '_0')"})
    unionFLyr.calculate(where=f"{unionBLDField}>=0",
                        calc_expression={"field": ID_FIELD_BLD_PARCELS_GEOPORTAL,
                                         "sqlExpression": "CONCAT(parcelid, '_1')"})

    return unionFLyr

try:
    inParcels = arcpy.GetParameter(0)
    minVolt = arcpy.GetParameterAsText(1)
    maxVolt = arcpy.GetParameterAsText(2)

    # debug only  *****************************
    # inParcels = r"G:\Users\Ardy\GIS\APRX\scratch.gdb\test_polys_nozm"
    # inParcels = r"G:\Users\Ardy\GIS\APRX\scratch.gdb\test_parcels_FEMA"
    # inParcels = r"G:\Users\JoseLuis\arcgis_scripts_enxco\site_metrics\test_parcels_FEMA.shp"
    # inParcels = r"G:\Users\JoseLuis\arcgis_scripts_enxco\site_metrics\Default.gdb\test_parcels_FEMA_v2"
    # inParcels = r"G:\Projects\USA_West\Flores\05_GIS\053_Data\Parcels_Flores_CoreLogic_TojLoad_LPM_20221024.shp"
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tract_Tests_20221115\Desktop_Outputs.gdb\WI_Solar_v03_TractID14285_Tract'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tract_Tests_20221115\Desktop_Outputs.gdb\OK_GRDA_v01_TractID1323_Tract'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tracts_SMT4_Desktop_Test_20221129.gdb\Test_10_cluster'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tracts_SMT4_Desktop_Test_20221129.gdb\Test_600_cluster'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tracts_SMT4_Desktop_Test_20221129.gdb\Test_5k_cluster'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tracts_SMT4_Desktop_Test_20221129.gdb\Test_1k_Tracts_IPC_over640acres'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tracts_SMT4_Desktop_Test_20221129.gdb\Test_5k_Tracts_IPC_over120acres'
    # inParcels = r'G:\Projects\USA_General\Siting_Tool_Development\Site_Metrics_Tool\Tests\Sample_Tracts_SMT4_Desktop_Test_20221129.gdb\Test_10k_Tracts_IPC_over_41acres'
    #
    # minVolt = ''
    # maxVolt = ''

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

    # InServTrans_Name   # PropTrans_Name         # InServSubs_Name     # PropSubs_Name
    # InServTrans_Miles  # PropTrans_Miles        # InServSubs_Miles    # PropSubs_Name

    rasterParams = namedtuple("rasterParams", "name id field")
    raster_inputs = [
        rasterParams('Forests_Only_From_LANDFIRE', 'ab97639707a846df87f7a2b6f4a91704', 'Forest'),
        rasterParams('Slope_over10perc_ned2usa_60m', '7136a66ef63148f69f2bf963a0778ce9', 'Slp10'),
        rasterParams('Soil_Bedrock_Depth_1_to_100cm_rc1_nogaps', '58d9638faa9f48f681e286cab4218402', 'BdRckSh'),
        rasterParams('Soil_Bedrock_Depth_101_to_300cm_rc1_nogaps', 'b13310e293b844c3a18c56d1712d8f2c', 'BdRckMD')
    ]
    vectorParams = namedtuple("vectorParams", "name id field")
    vector_inputs = [
        vectorParams("FEMA Flood Hazard Areas", '890e10f74f2441d2ae40398d2165b756', 'F100'),
        vectorParams("FEMA Flood Hazard Areas", 'ff98979c68a64666859ded394bb4d9a4', 'F500')
    ]

    transmissionWhereClause, substationWhereClause = getVoltageWhereClauses(minVolt, maxVolt)

    distanceParams = namedtuple("distanceParams", "name id sublayerid field whereclause ")
    distance_inputs = [
        distanceParams("Transmission_Lines_from_Velocity_Suite In Service", 'b3afb2c9f69a47cc8a3ddc9571c84856', '0',
                       'InServTrans', transmissionWhereClause),
        distanceParams("Transmission_Lines_from_Velocity_Suite Proposed", 'b3afb2c9f69a47cc8a3ddc9571c84856', '1',
                       'PropTrans', transmissionWhereClause),
        distanceParams('Substations_from_Velocity_Suite In Service', '978e2ef30e014722803bedbd126940e9', '0',
                       'InServSubs', substationWhereClause),
        distanceParams('Substations_from_Velocity_Suite Proposed', '978e2ef30e014722803bedbd126940e9', '1', 'PropSubs',
                       substationWhereClause)
    ]
    # inParcels = arcpy.FeatureSet(inParcels)
    # in case the OBJECTIDs are not starting at 1
    fc = arcpy.CopyFeatures_management(inParcels, 'memory/fc')
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

    df_list = []

    # the stats for each parcel are for the total of the parcel and for the buildable part of the parcel
    # prepare the input parcels and intersect with the buildable land
    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")

    arcpy.AddMessage("Fetching geoportal solar buildable land and holder for parcels")
    t0 = time.time()
    # find the solar national buildable land layer (National Solar Buildable Land)
    buildableItem = gis.content.get('754f20bf544d43c2bdfd7ff9e2713ddd')
    buildableLyr = buildableItem.layers[0]

    # find the site metric parcel layer (site_metrics_inputParcelsDEV)
    inputParcelsItem = gis.content.get('132c430f3c024fb08cf6368d52a3334a')

    inputParcelsLyr = inputParcelsItem.layers[0]
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # check if the site metric parcel layer is already in use
    numberOfParcels = inputParcelsLyr.query(where='1=1', return_count_only=True)
    if numberOfParcels > 0:
        arcpy.AddMessage("Tool already in used by another user")
        arcpy.SetParameterAsText(4, "Tool already in used by another user")
        os._exit(0)  # os._exit(0) doesn't execute the finally block and sys.exit() does

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

    arcpy.AddMessage("Uploading parcels to geoportal")
    t0 = time.time()
    inputParcelsLyr = uploadFeaturesToGeoportalLyr(inParcels, inputParcelsLyr, ID_FIELD_PARCELS_SDF)
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # Select intersecting buildable land into a new geoportal layer
    # to later download only this instead of making .query(spatialFilter) which fails too much
    arcpy.AddMessage("Selecting intersecting buildable features into a new geoportal layer")
    t0 = time.time()
    try:
        parcel_bld_item = gis.content.search('sitemetrics_selectedBuildableDEV', 'feature layer')[0]
        parcel_bld_item.delete()
    except Exception as e:
        pass

    # 00:00:58.45 seconds - intersect find_locations
    # find_locations - derive_new_locations returns partial feature records vs find_existing_locations was returning a much larger area\
    # 00:00:58.528 - withinDistance 0.1 feet find_locations
    selected_buildable_layer = find_locations.derive_new_locations(input_layers=[buildableLyr, inputParcelsLyr],
                                                                   expressions=[{"operator": "and",
                                                                                 "layer": 0,
                                                                                 "spatialRel": "withinDistance",
                                                                                 "selectingLayer": 1,
                                                                                 "distance": 0.001,
                                                                                 "units": "feet"}],
                                                                   output_name='sitemetrics_selectedBuildableDEV', context=context)
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # gis.content.search is for name specific & gis.content.get is for item id specific
    try:
        parcels_item = gis.content.search(parcelsBuildableUnionLayerName, 'feature layer')[0]  # sitemetrics_parcels_buildable_union
        parcels_item.delete()
    except Exception as e:
        pass

    arcpy.AddMessage("Converting parcels and selected buildable into feature classes")
    t0 = time.time()
    buildableArcgisFS = selected_buildable_layer.layers[0].query(where='1=1',  out_fields='objectid')
    buildableFS = arcpy.FeatureSet(buildableArcgisFS)
    arcpy.CopyFeatures_management(inParcels, 'memory/parc')
    # delete all fields from 'memory/parc' except the objectid and the shape
    parcfields = [f.name for f in arcpy.ListFields('memory/parc')]
    parcfields.remove('Shape')
    parcfields.remove('OBJECTID')
    arcpy.DeleteField_management('memory/parc', parcfields)
    arcpy.CopyFeatures_management(buildableFS, 'memory/build')
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    arcpy.AddMessage("Unionising parcels with solar national buildable land")
    t0 = time.time()
    buildParcUnion = arcpy.analysis.Union(['memory/parc', 'memory/build'], 'memory/parcBuildUnion')
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    arcpy.AddMessage("Removing buildable land outside the parcels")
    t0 = time.time()
    arcpy.CalculateField_management('memory/parcBuildUnion', "uniongpacres", "!shape.area@acres!", "PYTHON3", "",
                                    "DOUBLE")
    selectedLyr = arcpy.SelectLayerByAttribute_management('memory/parcBuildUnion', "NEW_SELECTION",
                                                          'FID_parc=-1 OR uniongpacres<0.5')
    arcpy.DeleteRows_management(selectedLyr)
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # repair geometry before uploading the union to geoportal
    arcpy.AddMessage("Creating unique field to track buildable land and non buildable land inside the parcel")
    t0 = time.time()
    unionSDF = pd.DataFrame.spatial.from_featureclass('memory/parcBuildUnion')

    # redo the parcelid and parcel_bld_id fields
    unionSDF.rename(columns={"FID_parc": ID_FIELD_PARCELS_GEOPORTAL}, inplace=True)
    unionSDF[ID_FIELD_BLD_PARCELS_GEOPORTAL] = unionSDF[ID_FIELD_PARCELS_GEOPORTAL].astype('string')+"_1"
    condition = unionSDF['FID_build']<1
    unionSDF.loc[condition, ID_FIELD_BLD_PARCELS_GEOPORTAL] = unionSDF[ID_FIELD_PARCELS_GEOPORTAL].astype('string')+"_0"
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # clean dataset
    arcpy.AddMessage("Uploading unionized parcels and buildable to geoportal")
    t0 = time.time()
    unionSDF = unionSDF[['parcelid', 'parcel_bld_id', 'uniongpacres', 'SHAPE']].copy()
    # the best is to upload this to geoportal is to use unionFLyr.append, not unionFLyr.edit_features(adds=unionSDF)
    # the problem is that unionFLyr.append needs to create a feature layer from the SDF first with unionSDF.spatial.to_featurelayer
    unionFLyr = unionSDF.spatial.to_featurelayer(title=parcelsBuildableUnionLayerName, service_name="sitemetrics_parcels_buildable_union_DEV")
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    arcpy.AddMessage("Summarizing areas by parcels and in and out buildable")
    t0 = time.time()
    # summarize area by parcelid
    parcelBuildableAcres = unionSDF.groupby([ID_FIELD_PARCELS_GEOPORTAL]).uniongpacres.sum()
    parcelBuildableAcres = parcelBuildableAcres.to_frame()
    parcelBuildableAcres.rename(columns={"uniongpacres": "Acres"}, inplace=True)

    df_list.append(parcelBuildableAcres)

    # summarize area by parcelsBuildableUnionIDField
    summarize_df = unionSDF.groupby(
        [ID_FIELD_PARCELS_GEOPORTAL, ID_FIELD_BLD_PARCELS_GEOPORTAL]).uniongpacres.sum().reset_index()

    # pivot table to convert parcelsBuildableUnionIDField to parcelid
    summarize_df['buildableIndex'] = summarize_df[ID_FIELD_BLD_PARCELS_GEOPORTAL].str[-1:]
    tmp_pivot_table = summarize_df.pivot_table(index=ID_FIELD_PARCELS_GEOPORTAL, columns='buildableIndex',
                                               values='uniongpacres')
    tmp_pivot_table.reset_index(inplace=True)
    tmp_pivot_table.rename(
        columns={'0': 'outBldAcres',
                 '1': 'inBldAcres'},
        inplace=True)

    df_list.append(tmp_pivot_table)

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # Make gp service calls asynchronously
    rasterToolbox = r'https://geoportal.edf-re.com/raggp/services;Other/getAcresAndPercRasterDEV;token={};{}'.format(
        gis._con.token, gis.url)
    vectorToolbox = r'https://geoportal.edf-re.com/raggp/services;Other/getAcresAndPercVectorDEV;token={};{}'.format(
        gis._con.token, gis.url)
    distanceToolbox = r'https://geoportal.edf-re.com/raggp/services;Other/getDistanceToNearestDEV;token={};{}'.format(
        gis._con.token, gis.url)
    arcpy.ImportToolbox(rasterToolbox)
    arcpy.ImportToolbox(vectorToolbox)
    arcpy.ImportToolbox(distanceToolbox)

    resultList = []

    arcpy.AddMessage("Making Raster Calls")
    t0 = time.time()
    # Make raster calls
    for tmp_raster in raster_inputs:
        tmp_raster_result = arcpy.getAcresAndPercRasterDEV.getAcresAndPercRasterDEV(parcelsBuildableUnionLayerName,
                                                                                    'tmp_run_id',
                                                                                    ID_FIELD_PARCELS_GEOPORTAL,
                                                                                    ID_FIELD_BLD_PARCELS_GEOPORTAL,
                                                                                    'uniongpacres',
                                                                                    tmp_raster.id,
                                                                                    tmp_raster.field)
        resultList.append(tmp_raster_result)

    arcpy.AddMessage("Making Vector Calls")
    # Make vector calls
    for tmp_vector in vector_inputs:
        tmp_vector_result = arcpy.getAcresAndPercVectorDEV.getAcresAndPercVectorDEV(parcelsBuildableUnionLayerName,
                                                                                    'tmp_run_id',
                                                                                    ID_FIELD_PARCELS_GEOPORTAL,
                                                                                    ID_FIELD_BLD_PARCELS_GEOPORTAL,
                                                                                    tmp_vector.id,
                                                                                    tmp_vector.field)
        resultList.append(tmp_vector_result)

    arcpy.AddMessage("Making Distance Calls")
    # Make distance calls
    for tmp_dist in distance_inputs:
        tmp_dist_result = arcpy.getDistanceToNearestDEV.getDistanceToNearestDEV(inputParcelsItem.id,
                                                                                'tmp_run_id',
                                                                                ID_FIELD_PARCELS_GEOPORTAL,
                                                                                tmp_dist.id,
                                                                                tmp_dist.sublayerid,
                                                                                tmp_dist.field,
                                                                                tmp_dist.whereclause)
        resultList.append(tmp_dist_result)

    # Wait for all the calls to be processed
    waitTimeStart = time.time()
    for tmp_result in resultList:
        while tmp_result.status < 4:
            time.sleep(0.2)
            waitTime = time.time() - waitTimeStart
            if waitTime > 1200:
                arcpy.AddMessage(f"Error: map service not responding. {tmp_result}")
                sys.exit()
        arcpy.AddMessage(f'{tmp_result.getOutput(1)}')

    # This is added to get the resultOutputs from our gp results list to a record set
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # Deleting old parcels in the geoportal layer
    arcpy.AddMessage("Deleting old parcels in the geoportal layer ")
    t0 = time.time()
    inputParcelsLyr.delete_features(where="1 = 1")
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
        df[ID_FIELD_PARCELS_GEOPORTAL] = df[ID_FIELD_PARCELS_GEOPORTAL].astype('int')
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

    parcelsWithStatsSDF = parcelsWithStatsSDF.replace(np.nan, 0)

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    # return the statistics recordset
    t0 = time.time()

    arcpy.AddMessage("Creating final record set")
    inParcelsWithStats_arcpyfset = arcpy.FeatureSet()
    inParcelsWithStats_arcgisfset = parcelsWithStatsSDF.spatial.to_featureset()
    inParcelsWithStats_arcpyfset.load(inParcelsWithStats_arcgisfset)
    arcpy.SetParameter(3, inParcelsWithStats_arcpyfset)

    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1 - t0)}")

    textResponse = f"### SITE METRICS COMPLETED SUCCESSFULLY BECAUSE I ROCK ###"
    arcpy.AddMessage(textResponse)
    arcpy.SetParameterAsText(4, textResponse)

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

finally:
    arcpy.AddMessage("Deleting old parcels in the geoportal layer ")
    inputParcelsItem = gis.content.get('132c430f3c024fb08cf6368d52a3334a')
    inputParcelsLyr = inputParcelsItem.layers[0]
    inputParcelsLyr.delete_features(where="1 = 1")

    arcpy.AddMessage("Deleting old unionized parcels and buildable geoportal layer")
    tmpItems = gis.content.search(parcelsBuildableUnionLayerName)
    for i in tmpItems:
        i.delete()
