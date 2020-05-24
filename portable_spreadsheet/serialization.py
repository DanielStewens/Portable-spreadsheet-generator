import abc
from typing import Tuple, List, Dict, Union, Callable, Optional
from types import MappingProxyType
from numbers import Number

import xlsxwriter
import numpy

from .cell_type import CellType

# ==== TYPES ====
# Type for the output dictionary with the
#   logic: 'columns'/'rows' -> col/row key -> 'rows'/'columns' -> row/col key
#   -> (pseudo)language -> value
T_out_dict = Dict[
    str,  # 'Rows'/'Columns'
    Dict[
        object,  # Rows/Column key
        Union[
            # For values:
            Dict[
                str,  # 'Columns'/'Rows' (in iversion order to above)
                Union[
                    Dict[object, Dict[str, Union[str, float]]],  # Values
                    str  # For help text
                     ]
                ],
            str  # For help text
            ]
    ]
]
# ===============


class Serialization(abc.ABC):
    """Provides basic functionality for exporting to required formats.

    Attributes:
        export_offset (Tuple[int, int]): Defines how many rows and
            columns are skiped from the left top corner. First index is
            number of rows, second number of columns.
        warning_logger (Callable[[str], None]): Function that logs the
            warnings.
        export_subset (bool): If true, warning are raised when exporting.
    """

    def __init__(self, *,
                 export_offset: Tuple[int, int] = (0, 0),
                 export_subset: bool = False,
                 warning_logger: Optional[Callable[[str], None]] = None):
        """Initialise functionality for serialization.

        Args:
            export_offset (Tuple[int, int]): Defines how many rows and
                columns are skiped from the left top corner. First index is
                number of rows, second number of columns.
            export_subset (bool): If true, warning are raised when exporting.
            warning_logger (Optional[Callable[[str], None]]): Function that
                logs the warnings (or None if skipped).
        """
        # Export offset of rows, columns
        self.export_offset: Tuple[int, int] = export_offset
        if warning_logger is not None:
            self.warning_logger: Callable[[str], None] = warning_logger
        else:
            # Silent logger
            self.warning_logger: Callable[[str], None] = lambda _mess: _mess
        self.export_subset: bool = export_subset

    @property
    def shape(self) -> Tuple[int, int]:
        """Get the shape as the tuple of number of rows and columns.

        Returns:
            Tuple[int, int]: number of rows, columns
        """
        raise NotImplementedError

    @property
    def cell_indices(self) -> 'CellIndices':
        """Get the cell indices.

        Returns:
            CellIndices: Cell indices of the spreadsheet.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def _get_cell_at(self, row: int, column: int) -> 'Cell':
        """Get the particular cell on the (row, column) position.

        Returns:
            Cell: The call on given position.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def _get_variables(self) -> '_SheetVariables':
        """Return the sheet variables as _SheetVariables object.

        Returns:
            _SheetVariables: Sheet variables.
        """
        raise NotImplementedError

    def log_export_subset_warning_if_needed(self):
        """Log the export subset warning if needed.
        """
        if self.export_subset:
            self.warning_logger("Slice is being exported => there is"
                                " a possibility of data losses.")

    def to_excel(self,
                 file_path: str,
                 /, *,  # noqa E999
                 sheet_name: str = "Results",
                 spaces_replacement: str = ' ',
                 label_row_format: dict = {'bold': True},
                 label_column_format: dict = {'bold': True},
                 variables_sheet_name: Optional[str] = None,
                 variables_sheet_header: Dict[str, str] = MappingProxyType(
                     {
                         "name": "Name",
                         "value": "Value",
                         "description": "Description"
                     })
                 ) -> None:
        """Export the values inside Spreadsheet instance to the
            Excel 2010 compatible .xslx file

        Args:
            file_path (str): Path to the target .xlsx file.
            sheet_name (str): The name of the sheet inside the file.
            spaces_replacement (str): All the spaces in the rows and columns
                descriptions (labels) are replaced with this string.
            label_row_format (dict): Excel styles for the label of rows,
                documentation: https://xlsxwriter.readthedocs.io/format.html
            label_column_format (dict): Excel styles for the label of columns,
                documentation: https://xlsxwriter.readthedocs.io/format.html
            variables_sheet_name (Optional[str]): If set, creates the new
                sheet with variables and their description and possibility
                to set them up (directly from the sheet).
            variables_sheet_header (Dict[str, str]): Define the labels (header)
                for the sheet with variables (first row in the sheet).
        """
        # Quick sanity check
        if ".xlsx" not in file_path[-5:]:
            raise ValueError("Suffix of the file has to be '.xslx'!")
        if not isinstance(sheet_name, str) or len(sheet_name) < 1:
            raise ValueError("Sheet name has to be non-empty string!")
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        # Open or create an Excel file and create a sheet inside:
        workbook = xlsxwriter.Workbook(file_path)
        worksheet = workbook.add_worksheet(name=sheet_name)
        # Register the style for the labels:
        col_label_format = workbook.add_format(label_column_format)
        row_label_format = workbook.add_format(label_row_format)

        # Register all variables:
        if self._get_variables().empty:
            pass
        elif variables_sheet_name is None:
            for name, value in self._get_variables().variables_dict.items():
                workbook.define_name(name, str(value['value']))
        else:
            variables_sheet = workbook.add_worksheet(name=variables_sheet_name)
            # Insert header (labels)
            variables_sheet.write(0, 0, variables_sheet_header['name'],
                                  col_label_format)
            variables_sheet.write(0, 1, variables_sheet_header['value'],
                                  col_label_format)
            variables_sheet.write(0, 2, variables_sheet_header['description'],
                                  col_label_format)
            row_idx = 1
            for var_n, var_v in self._get_variables().variables_dict.items():
                # Insert variables to the sheet
                variables_sheet.write(row_idx, 0, var_n)
                variables_sheet.write(row_idx, 1, var_v['value'])
                variables_sheet.write(row_idx, 2, var_v['description'])
                # Register variable
                workbook.define_name(
                    var_n, f'={variables_sheet_name}!$B${row_idx + 1}'
                )
                row_idx += 1

        # Iterate through all columns and rows and add data
        for row_idx in range(self.shape[0]):
            for col_idx in range(self.shape[1]):
                cell: 'Cell' = self._get_cell_at(row_idx, col_idx)
                if cell.value is not None:
                    # Offset here is either 0 or 1, indicates if we writes
                    # row/column labels to the first row and column.
                    offset = 0
                    if self.cell_indices.excel_append_labels:
                        offset = 1
                    # Excel format/style for the cell:
                    if len(cell.excel_format) > 0:
                        # Register the format
                        cell_format = workbook.add_format(cell.excel_format)
                    else:
                        cell_format = None
                    if cell.cell_type == CellType.value_only:
                        # If the cell is a value only, use method 'write'
                        worksheet.write(row_idx + offset,
                                        col_idx + offset,
                                        cell.value,
                                        cell_format)
                    else:
                        # If the cell is a formula, use method 'write_formula'
                        worksheet.write_formula(row_idx + offset,
                                                col_idx + offset,
                                                cell.parse['excel'],
                                                value=cell.value,
                                                cell_format=cell_format)
        # Add the labels for rows and columns
        if self.cell_indices.excel_append_labels:
            # Add labels of column
            for col_idx in range(self.shape[1]):
                worksheet.write(0,
                                col_idx + 1,
                                self.cell_indices.columns_labels[
                                    # Reflect the export offset
                                    col_idx + self.export_offset[1]
                                ].replace(' ', spaces_replacement),
                                col_label_format)
            # Add labels for rows
            for row_idx in range(self.shape[0]):
                worksheet.write(row_idx + 1,
                                0,
                                self.cell_indices.rows_labels[
                                    # Reflect the export offset
                                    row_idx + self.export_offset[0]
                                ].replace(' ', spaces_replacement),
                                row_label_format)
        # Store results
        workbook.close()

    def to_dictionary(self,
                      languages: List[str] = None,
                      /, *,  # noqa E999
                      by_row: bool = True,
                      languages_pseudonyms: List[str] = None,
                      spaces_replacement: str = ' ',
                      skip_nan_cell: bool = False,
                      nan_replacement: object = None) -> T_out_dict:
        """Export this spreadsheet to the dictionary that can be parsed to the
            JSON format.

        Args:
            languages (List[str]): List of languages that should be exported.
                If it has value None, all the languages are exported.
            by_row (bool): If True, rows are the first indices and columns
                are the second in the order. If False it is vice-versa.
            languages_pseudonyms (List[str]): Rename languages to the strings
                inside this list.
            spaces_replacement (str): All the spaces in the rows and columns
                descriptions (labels) are replaced with this string.
            skip_nan_cell (bool): If True, None (NaN) values are skipped.
            nan_replacement (object): Replacement for the None (NaN) value

        Returns:
            Dict[object, Dict[object, Dict[str, Union[str, float]]]]:
                Dictionary with keys: 1. column/row, 2. row/column, 3. language
                or language pseudonym or 'value' keyword for values -> value as
                a value or as a cell building string.
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        # Assign all languages if languages is None:
        if languages is None:
            languages = self.cell_indices.languages
        # Quick sanity check:
        if (
                languages_pseudonyms is not None
                and len(languages_pseudonyms) != len(languages)
        ):
            raise ValueError("Language pseudonyms does not have the same size "
                             "as the language array!")
        # Language array (use pseudonyms if possible, language otherwise)
        languages_used = languages
        if languages_pseudonyms is not None:
            languages_used = languages_pseudonyms
        # If by column (not by_row)

        # A) The x-axes represents the columns
        x_range = self.shape[1]
        x = [label.replace(' ', spaces_replacement)
             for label in self.cell_indices.columns_labels[
                          # Reflects the column offset for export
                          self.export_offset[1]:
                          ]
             ]
        if (x_helptext := self.cell_indices.columns_help_text) is not None:  # noqa E203
            # Reflects the column offset for export
            x_helptext = x_helptext[self.export_offset[1]:]
        x_start_key = 'columns'
        # The y-axes represents the rows
        y_range = self.shape[0]
        y = [label.replace(' ', spaces_replacement)
             for label in self.cell_indices.rows_labels[
                          # Reflects the row offset for export
                          self.export_offset[0]:
                          ]
             ]
        if (y_helptext := self.cell_indices.rows_help_text) is not None:  # noqa E203
            # Reflects the row offset for export
            y_helptext = y_helptext[self.export_offset[0]:]
        y_start_key = 'rows'

        # B) The x-axes represents the rows:
        if by_row:
            x_range = self.shape[0]
            x = [label.replace(' ', spaces_replacement)
                 for label in self.cell_indices.rows_labels[
                          # Reflects the row offset for export
                          self.export_offset[0]:
                          ]
                 ]
            if (x_helptext := self.cell_indices.rows_help_text) is not None:  # noqa E203
                # Reflects the row offset for export
                x_helptext = x_helptext[self.export_offset[0]:]
            x_start_key = 'rows'
            # The y-axes represents the columns
            y_range = self.shape[1]
            y = [label.replace(' ', spaces_replacement)
                 for label in self.cell_indices.columns_labels[
                          # Reflects the column offset for export
                          self.export_offset[1]:
                          ]]
            if (y_helptext := self.cell_indices.columns_help_text) is not None:  # noqa E203
                # Reflects the column offset for export
                y_helptext = y_helptext[self.export_offset[1]:]
            y_start_key = 'columns'

        # Export the spreadsheet to the dictionary (that can by JSON-ified)
        values = {x_start_key: {}}
        for idx_x in range(x_range):
            y_values = {y_start_key: {}}
            for idx_y in range(y_range):
                # Select the correct cell
                if by_row:
                    cell = self._get_cell_at(idx_x, idx_y)
                else:
                    cell = self._get_cell_at(idx_y, idx_x)
                # Skip if cell value is None if required:
                cell_value = cell.value
                if cell_value is None and skip_nan_cell:
                    continue
                # Replace the NaN value as required
                if cell_value is None:
                    cell_value = nan_replacement
                # Receive values from cell (either integer or building text)
                parsed_cell = cell.parse
                pseudolang_and_val = {}
                for i, language in enumerate(languages):
                    pseudolang_and_val[languages_used[i]] = \
                        parsed_cell[language]
                # Append the value:
                pseudolang_and_val['value'] = cell_value
                pseudolang_and_val['description'] = cell.description
                y_values[y_start_key][y[idx_y]] = pseudolang_and_val
                if y_helptext is not None:
                    y_values[y_start_key][y[idx_y]]['help_text'] = \
                        y_helptext[idx_y]
            values[x_start_key][x[idx_x]] = y_values
            if x_helptext is not None:
                values[x_start_key][x[idx_x]][
                    'help_text'] = x_helptext[idx_x]
        # Add variables
        values['variables'] = self._get_variables().variables_dict
        # Add a row and column labels as arrays
        if by_row:
            values['row-labels'] = x
            values['column-labels'] = y
        else:
            values['row-labels'] = y
            values['column-labels'] = x
        return values

    def to_string_of_values(self) -> str:
        """Export values inside table to the Python array definition string.

        Returns:
            str: Python list definition string.
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        export = "["
        for row_idx in range(self.shape[0]):
            export += "["
            for col_idx in range(self.shape[1]):
                export += str(self._get_cell_at(row_idx, col_idx).value)
                if col_idx < self.shape[1] - 1:
                    export += ', '
            export += "]"
            if row_idx < self.shape[0] - 1:
                export += ",\n"
        return export + "]"

    def to_2d_list(self) -> List[List[object]]:
        """Export values 2 dimensional Python array.

        Returns:
            str: Python array.
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        export: list = []
        for row_idx in range(self.shape[0]):
            row: list = []
            for col_idx in range(self.shape[1]):
                row.append(self._get_cell_at(row_idx, col_idx).value)
            export.append(row)
        return export

    def to_csv(self, *,
               spaces_replacement: str = ' ',
               top_right_corner_text: str = "Sheet",
               sep: str = ',',
               line_terminator: str = '\n',
               na_rep: str = '') -> str:
        """Export values to the string in the CSV logic

        Args:
            spaces_replacement (str): All the spaces in the rows and columns
                descriptions (labels) are replaced with this string.
            top_right_corner_text (str): Text in the top right corner.
            sep (str): Separator of values in a row.
            line_terminator (str): Ending sequence (character) of a row.
            na_rep (str): Replacement for the missing data.

        Returns:
            str: CSV of the values
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        export = ""
        for row_idx in range(-1, self.shape[0]):
            if row_idx == -1:
                export += top_right_corner_text + sep
                # Insert labels of columns:
                for col_i in range(self.shape[1]):
                    col = self.cell_indices.columns_labels[
                        col_i + self.export_offset[1]
                    ]
                    export += col.replace(' ', spaces_replacement)
                    if col_i < self.shape[1] - 1:
                        export += sep
            else:
                # Insert labels of rows
                export += self.cell_indices.rows_labels[
                              row_idx + self.export_offset[0]
                          ].replace(' ', spaces_replacement) + sep
                # Insert actual values in the spreadsheet
                for col_idx in range(self.shape[1]):
                    value = self._get_cell_at(row_idx, col_idx).value
                    if value is None:
                        value = na_rep
                    export += str(value)
                    if col_idx < self.shape[1] - 1:
                        export += sep
            if row_idx < self.shape[0] - 1:
                export += line_terminator
        return export

    def to_markdown(self, *,
                    spaces_replacement: str = ' ',
                    top_right_corner_text: str = "Sheet",
                    na_rep: str = ''):
        """Export values to the string in the Markdown (MD) file logic

        Args:
            spaces_replacement (str): All the spaces in the rows and columns
                descriptions (labels) are replaced with this string.
            top_right_corner_text (str): Text in the top right corner.
            na_rep (str): Replacement for the missing data.

        Returns:
            str: Markdown (MD) compatible table of the values
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        export = ""
        for row_idx in range(-2, self.shape[0]):
            if row_idx == -2:
                # Add the labels and top right corner text
                export += "| " + top_right_corner_text + " |"
                for col_i in range(self.shape[1]):
                    # Insert column labels:
                    col = self.cell_indices.columns_labels[
                        col_i + self.export_offset[1]
                    ]
                    export += "*" + col.replace(' ', spaces_replacement) + "*"
                    if col_i < self.shape[1] - 1:
                        export += " | "
                    elif col_i == self.shape[1] - 1:
                        export += " |\n"

            elif row_idx == -1:
                # Add the separator to start the table body:
                export += "|----|"
                for col_i in range(self.shape[1]):
                    export += "----|"
                    if col_i == self.shape[1] - 1:
                        export += "\n"
            else:
                export += "| *"
                # Insert row labels
                export += self.cell_indices.rows_labels[
                              row_idx + self.export_offset[0]
                          ].replace(' ', spaces_replacement)
                export += "*" + " | "

                for col_idx in range(self.shape[1]):
                    value = self._get_cell_at(row_idx, col_idx).value
                    if value is None:
                        value = na_rep
                    export += str(value)
                    if col_idx < self.shape[1] - 1:
                        export += " | "
                    elif col_idx == self.shape[1] - 1:
                        export += " |\n"
        return export

    def to_numpy(self) -> numpy.ndarray:
        """Exports the values to the numpy.ndarray.

        Returns:
            numpy.ndarray: 2 dimensions array with values
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        results = numpy.zeros(self.shape)
        # Variable for indicating that logging is needed (for logging that
        # replacement of some value for NaN is done):
        contains_nonumeric_values = False
        for row_idx in range(self.shape[0]):
            for col_idx in range(self.shape[1]):
                if (value := self._get_cell_at(row_idx, col_idx).value) is not None:  # noqa E999
                    if isinstance(value, Number):
                        results[row_idx, col_idx] = value
                    else:
                        results[row_idx, col_idx] = numpy.nan
                        # For logging that replacement is done
                        contains_nonumeric_values = True
                else:
                    results[row_idx, col_idx] = numpy.nan
        # Log warning if needed
        if contains_nonumeric_values:
            self.warning_logger(
                "Some values in the sheet are not numbers, the "
                "nan value is set instead."
            )
        return results

    def to_html_table(self, *,
                      spaces_replacement: str = ' ',
                      top_right_corner_text: str = "Sheet",
                      na_rep: str = '',
                      language_for_description: str = None) -> str:
        """Export values to the string in the HTML table logic

        Args:
            spaces_replacement (str): All the spaces in the rows and columns
                descriptions (labels) are replaced with this string.
            top_right_corner_text (str): Text in the top right corner.
            na_rep (str): Replacement for the missing data.
            language_for_description (str): If not None, the description
                of each computational cell is inserted as word of this
                language (if the property description is not set).

        Returns:
            str: HTML table definition
        """
        # Log warning if needed
        self.log_export_subset_warning_if_needed()

        export = "<table>"
        for row_idx in range(-1, self.shape[0]):
            export += "<tr>"
            if row_idx == -1:
                export += "<th>"
                export += top_right_corner_text
                export += "</th>"
                # Insert labels of columns:
                for col_i in range(self.shape[1]):
                    export += "<th>"
                    col = self.cell_indices.columns_labels[
                        col_i + self.export_offset[1]
                        ]
                    if (help_text := self.cell_indices.columns_help_text) \
                            is not None:
                        title_attr = ' title="{}"'.format(
                            help_text[col_i + self.export_offset[1]]
                        )
                    else:
                        title_attr = ""
                    export += f'<a href="javascript:;" {title_attr}>'
                    export += col.replace(' ', spaces_replacement)
                    export += "</a>"
                    export += "</th>"
            else:
                # Insert labels of rows
                if (help_text := self.cell_indices.rows_help_text) \
                        is not None:
                    title_attr = ' title="{}"'.format(
                        help_text[row_idx + self.export_offset[1]]
                    )
                else:
                    title_attr = ""
                export += "<td>"
                export += f'<a href="javascript:;" {title_attr}>'
                export += self.cell_indices.rows_labels[
                              row_idx + self.export_offset[0]
                              ].replace(' ', spaces_replacement)
                export += "</a>"
                export += "</td>"
                # Insert actual values in the spreadsheet
                for col_idx in range(self.shape[1]):
                    title_attr = ""
                    cell_at_pos = self._get_cell_at(row_idx, col_idx)
                    if (description := cell_at_pos.description) \
                            is not None:
                        title_attr = ' title="{}"'.format(description)
                    elif language_for_description is not None:
                        if cell_at_pos.cell_type == CellType.computational:
                            title = cell_at_pos.constructing_words.words[
                                language_for_description
                            ]
                            title_attr = f' title="{title}"'
                    export += "<td>"
                    export += f'<a href="javascript:;" {title_attr}>'
                    value = cell_at_pos.value
                    if value is None:
                        value = na_rep
                    export += str(value)
                    export += "</a>"
                    export += "</td>"
            export += '</tr>'
        export += '</table>'
        return export