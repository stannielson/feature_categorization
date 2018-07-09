"""
Title:   CategorizeFeatureGeometry

Author:  Stanton K. Nielson
         GIS Specialist
         Bureau of Land Management
         Wyoming High Desert District
         snielson@blm.gov
        
Date:    February 14, 2018

Version: 3.0
"""


import arcpy
import datetime
import string


class CategorizeFeatureGeometry(object):
    

    def __init__(self, target_features, division_features, division_field,
                 output_features, output_field, overrun=False,
                 include_uncategorized=False, workspace='in_memory'):
        

        """
        CategorizeFeatureGeometry
        -----------------------------------------------------------------------
        This geoprocessing script categorizes feature geometry based on a
        supplied polygon dataset (and corresponding categorical field).
        Depending on the supplied arguments the script will divide up the
        feature geometry or identify geometry based on intersection in a
        target dataset.  The output dataset will contain geometry with
        category attributes to which users can apply definition queries.
        Additionally, this script can also retain uncategorized data based on
        user-supplied preference.

        This version expands previous capabilities by allowing both text and
        numeric categorization (excluding OID and Geometry types), improving
        category recognition, increased validation measures, integrated
        geoprocessing parameterization, performance improvement, workspace
        specification, and transition to an object-oriented design.
        -----------------------------------------------------------------------
        target_features (string):           the input features to be
                                            categorized
        division_features (string):         the polygon features used for
                                            categorization
        division_field (string):            the field that contains category
                                            values in the division features
        output_features (string):           the resulting categorized features
        output_field (string):              the field that contains category
                                            values in the output features
        overrun (boolean):                  allows target features to overlap
                                            category boundaries
        include_uncategorized (boolean):    retains uncategorized features
        workspace (string):                 location where processing occurs
                                            (a provided path will allow
                                            processing for a larger dataset
                                            that would otherwise overwhelm the
                                            'in_memory' environment)
        -----------------------------------------------------------------------       
        """


        self.target_features = target_features
        self.division_features = division_features
        self.division_field = division_field
        self.output_features = output_features
        self.output_field = output_field
        self.overrun = overrun
        self.include_uncategorized = include_uncategorized
        self.workspace = workspace

        self.__set_geoprocessing_workspace(self.workspace)

        self.timestamp = self.__create_timestamp()
        self.attribute_set = self.__get_unique_attributes()
        self.parameter_dictionary = self.__create_parameter_dictionary()
        
        self.division_field_properties = self.__get_division_field_properties()
        self.__validate_output_field_name()
        self.output_field_properties = self.__set_output_field_properties()

        self.__validate_criteria()

        self.target_layer = self.__create_target_layer()
        self.__add_category_field()
        self.__categorize_target_layer()

        self.__delete_intermediary_data()


    def __get_unique_attributes(self):
        
        arcpy.AddMessage('Scanning categories...')
        return set(target_row.getValue(self.division_field)
                   for target_row in arcpy.SearchCursor(
                       self.division_features))


    def __get_division_field_properties(self):
        
        division_fields = arcpy.ListFields(self.division_features)
        for field in division_fields:
            if field.name == self.division_field:
                return {'field_name':      field.name,
                        'field_type':      field.type,
                        'field_length':    field.length,
                        'field_precision': field.precision,
                        'field_scale':     field.scale}


    def __set_geoprocessing_workspace(self, path):
        arcpy.env.workspace = path


    def __set_output_field_properties(self):
        
        field_properties = {
            i: self.division_field_properties[i]
            if self.division_field_properties[i] != 0 else None
            for i in self.division_field_properties}
        key_removal_list = list()
        for key in field_properties:
            if not field_properties[key]:
                key_removal_list.append(key)
        for key in key_removal_list:
            field_properties.pop(key)
        field_properties['field_type'] = field_properties['field_type'].upper()
        field_properties['field_name'] = self.output_field
        return field_properties


    def __create_timestamp(self):
        
        return str(hex(int(datetime.datetime.utcnow().strftime(
            '%Y%m%d%H%M%S'))).rstrip('L').lstrip('0x'))


    def __create_parameter_dictionary(self):
        
        return {i:{'category': list(self.attribute_set)[i],
                   'category_file': 'tmp_cat_{}_{}'.format(i, self.timestamp),
                   'division_file': 'tmp_div_{}_{}'.format(i, self.timestamp),
                   'criteria': list(self.attribute_set)[i]}
                for i in range(0, len(self.attribute_set))}


    def __validate_criteria(self):
        
        if self.output_field_properties['field_type'] == 'STRING':
            for key in self.parameter_dictionary:
                self.parameter_dictionary[key][
                    'criteria'] = self.parameter_dictionary[key][
                        'criteria'].replace('\'', '\'\'')
                self.parameter_dictionary[key][
                    'criteria'] = '\'' + self.parameter_dictionary[key][
                        'criteria'] + '\''


    def __create_target_layer(self):
        
        replicated_target_features = 'tmp_rep_{}'.format(self.timestamp)
        target_layer = 'tmp_lyr_{}'.format(self.timestamp)
        arcpy.CopyFeatures_management(
            in_features=self.target_features,
            out_feature_class=replicated_target_features)
        arcpy.MakeFeatureLayer_management(
            in_features=replicated_target_features,
            out_layer=target_layer)                  
        return target_layer


    def __add_category_field(self):
        
        arcpy.AddField_management(in_table=self.target_layer,
                                  **self.output_field_properties)


    def __delete_intermediary_data(self):
        
        if self.workspace != 'in_memory':
            delete_list = [
                delete_file for delete_file in
                arcpy.ListFeatureClasses('tmp_*{}*'.format(self.timestamp))]
            for delete_file in delete_list:
                arcpy.Delete_management(delete_file)
        else:
            arcpy.Delete_management(self.workspace)


    def __validate_output_field_name(self):

        for i in string.punctuation.replace('_',''):
            self.output_field = self.output_field.replace(i, '')

        if self.output_field[0].isdigit():
            self.output_field = 'Field_{}'.format(self.output_field)

        if ' ' in self.output_field:
            self.output_field = self.output_field.replace(' ', '_')
        
        if ((self.workspace == 'in_memory' or '.gdb' in self.workspace) and
            '.shp' not in self.output_features):
            self.output_field = self.output_field[:64]
        else:
            self.output_field = self.output_field[:10]


    def __categorize_target_layer(self):
        
        arcpy.AddMessage('Categorizing target features...')
        temporary_output = 'tmp_out_{}'.format(self.timestamp)
        
        for key in self.parameter_dictionary:
            arcpy.AddMessage('Processing category {} of {}...'.format(
                key+1, len(self.parameter_dictionary)))
            arcpy.Select_analysis(
                in_features = self.division_features,
                out_feature_class = self.parameter_dictionary[key][
                    'division_file'],
                where_clause = '{} = {}'.format(
                    arcpy.AddFieldDelimiters(self.division_features,
                                             self.division_field),
                    self.parameter_dictionary[key]['criteria']))

            if not self.overrun:
                arcpy.Clip_analysis(
                    in_features=self.target_layer,
                    clip_features=self.parameter_dictionary[key][
                        'division_file'],
                    out_feature_class=self.parameter_dictionary[key][
                        'category_file'])
            else:
                arcpy.SelectLayerByLocation_management(
                    in_layer=self.target_layer,
                    overlap_type='INTERSECT',
                    select_features=self.parameter_dictionary[key][
                        'division_file'])
                temporary_select_layer = 'tmp_sel_lyr_{}'.format(
                    self.timestamp)
                arcpy.MakeFeatureLayer_management(
                    in_features=self.target_layer,
                    out_layer=temporary_select_layer)
                arcpy.CopyFeatures_management(
                    in_features=temporary_select_layer,
                    out_feature_class=self.parameter_dictionary[key][
                        'category_file'])
                arcpy.Delete_management(in_data=temporary_select_layer)

            arcpy.CalculateField_management(
                in_table=self.parameter_dictionary[key]['category_file'],
                field=self.output_field_properties['field_name'],
                expression='{}{}{}'.format(
                    'r"', self.parameter_dictionary[key]['category'], '"'),
                expression_type='PYTHON_9.3')

            if not arcpy.Exists(temporary_output):
                arcpy.CopyFeatures_management(
                    in_features=self.parameter_dictionary[key][
                        'category_file'],
                    out_feature_class=temporary_output)
            else:
                arcpy.Append_management(
                    inputs=self.parameter_dictionary[key][
                        'category_file'],
                    target=temporary_output)

        if self.include_uncategorized:
            arcpy.AddMessage('Processing uncategorized features...')
            uncategorized_features = 'tmp_unc_fea_{}'.format(self.timestamp)
            arcpy.SelectLayerByAttribute_management(
                in_layer_or_view=self.target_layer,
                selection_type='CLEAR_SELECTION')
            arcpy.Erase_analysis(
                in_features=self.target_layer,
                erase_features=temporary_output,
                out_feature_class=uncategorized_features)
            arcpy.Append_management(
                inputs=uncategorized_features,
                target=temporary_output,
                schema_type='NO_TEST')

        arcpy.AddMessage('Deduplicating data...')
        
        ignore_field_types = ('Geometry', 'GlobalID', 'GUID', 'OID')

        deduplicated_output= 'tmp_ded_{}'.format(self.timestamp)
        deduplication_fields = {
            field.name if field.type not in ignore_field_types else None
            for field in arcpy.ListFields(temporary_output)}
        deduplication_fields.remove(None)
        deduplication_fields = list(deduplication_fields)
        arcpy.Dissolve_management(
            in_features=temporary_output,
            out_feature_class=deduplicated_output,
            dissolve_field=deduplication_fields)

        arcpy.AddMessage('Generating output features...')
        arcpy.CopyFeatures_management(
            in_features=deduplicated_output,
            out_feature_class=self.output_features)


if __name__ == '__main__':

    received_parameters = list(arcpy.GetParameter(i) for i in
                               range(arcpy.GetArgumentCount()))

    if len(received_parameters) == 7:
        received_parameters.append('in_memory')
    
    input_parameters = {
        'target_features':        str(received_parameters[0]),
        'division_features':      str(received_parameters[1]),
        'division_field':         str(received_parameters[2]),
        'output_features':        str(received_parameters[3]),
        'output_field':           str(received_parameters[4]),
        'overrun':                received_parameters[5],
        'include_uncategorized':  received_parameters[6],
        'workspace':              str(received_parameters[7])
        }

    execute_process = CategorizeFeatureGeometry(**input_parameters)
    
            
