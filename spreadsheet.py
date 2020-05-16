from typing import Tuple, List, Optional, Dict, Union
import copy

import xlsxwriter

from cell import Cell
from cell_indices import CellIndices
from cell_type import CellType

# ==== TYPES ====
# Type for the sheet (list of the list of the cells)
T_sheet = List[List[Cell]]
# Type for the output dictionary with the
#   logic: col/row key -> row/col key -> (pseudo)language -> value
T_out_dict = Dict[object, Dict[object, Dict[str, Union[str, float]]]]
# ===============


class Spreadsheet(object):
    class _Location(object):
        def __init__(self,
                     spreadsheet: 'Spreadsheet',
                     by_integer: bool):
            self.spreadsheet: 'Spreadsheet' = spreadsheet
            self.by_integer: str = by_integer

        def __setitem__(self, index, val):
            if self.by_integer:
                self.spreadsheet._set_item(val, index, None)
            else:
                self.spreadsheet._set_item(val, None, index)

        def __getitem__(self, index):
            if self.by_integer:
                return self.spreadsheet._get_item(index, None)
            else:
                return self.spreadsheet._get_item(None, index)

    def __init__(self,
                 cell_indices: CellIndices):
        self.cell_indices: CellIndices = copy.deepcopy(cell_indices)

        self._sheet: T_sheet = self._initialise_array()
        # To make cells accessible using obj.loc[nick_x, nick_y]
        self.iloc = self._Location(self, True)
        # To make cells accessible using obj.iloc[pos_x, pos_y]
        self.loc = self._Location(self, False)

    def _initialise_array(self) -> T_sheet:
        array: T_sheet = []
        for row in range(self.cell_indices.shape[0]):
            row: List[Cell] = []
            for col in range(self.cell_indices.shape[1]):
                row.append(Cell(cell_indices=self.cell_indices))
            array.append(row)
        return array

    def _set_item(self, value,
                  index_integer: Tuple[int, int] = None,
                  index_nickname: Tuple[object, object] = None):
        if index_integer is not None and index_nickname is not None:
            raise ValueError("Only one of parameters 'index_integer' and"
                             "'index_nickname' has to be set!")
        if index_nickname is not None:
            _x = self.cell_indices.rows_nicknames.index(index_nickname[0])
            _y = self.cell_indices.rows_nicknames.index(index_nickname[1])
            index_integer = (_x, _y)
        if index_integer is not None:
            _value = value
            if not isinstance(value, Cell):
                _value = Cell(index_integer[0], index_integer[1],
                              value=value, cell_indices=self.cell_indices)
            self._sheet[index_integer[0]][index_integer[1]] = _value

    def _get_item(self,
                  index_integer: Tuple[int, int] = None,
                  index_nickname: Tuple[object, object] = None) -> Cell:
        if index_integer is not None and index_nickname is not None:
            raise ValueError("Only one of parameters 'index_integer' and"
                             "'index_nickname' has to be set!")
        if index_nickname is not None:
            _x = self.cell_indices.rows_nicknames.index(index_nickname[0])
            _y = self.cell_indices.rows_nicknames.index(index_nickname[1])
            index_integer = (_x, _y)
        if index_integer is not None:
            return self._sheet[index_integer[0]][index_integer[1]]

    @property
    def shape(self) -> Tuple[int]:
        return self.cell_indices.shape[0], self.cell_indices.shape[1]

    def reshape(self,
                cell_indices: CellIndices,
                in_place: bool = True) -> Optional['Spreadsheet']:
        # TODO
        pass

    def to_excel(self, file_path: str, sheet_name: str = "Results") -> None:
        """Export the values inside Spreadsheet instance to the
            Excel 2010 compatible .xslx file

        Args:
            file_path (str): Path to the target .xlsx file.
            sheet_name (str): The name of the sheet inside the file.
        """
        # Quick sanity check
        if ".xlsx" not in file_path[-5:]:
            raise ValueError("Suffix of the file has to be '.xslx'!")
        if not isinstance(sheet_name, str) or len(sheet_name) < 1:
            raise ValueError("Sheet name has to be non-empty string!")
        # Open or create an Excel file and create a sheet inside:
        workbook = xlsxwriter.Workbook(file_path)
        worksheet = workbook.add_worksheet(name=sheet_name)
        # Iterate through all columns and rows and add data
        for row_idx in range(self.shape[0]):
            for col_idx in range(self.shape[1]):
                cell: Cell = self.iloc[row_idx, col_idx]
                if cell.value is not None:
                    if cell.cell_type == CellType.value_only:
                        # If the cell is a value only, use method 'write'
                        worksheet.write(row_idx, col_idx, cell.value)
                    else:
                        # If the cell is a formula, use method 'write_formula'
                        worksheet.write_formula(row_idx,
                                                col_idx,
                                                cell.parse['excel'],
                                                value=cell.value)
        # Store results
        workbook.close()

    def to_dictionary(self,
                      languages: List[str] = None, /, *,
                      by_row: bool = True,
                      languages_pseudonyms: List[str] = None) -> T_out_dict:
        """Export this spreadsheet to the dictionary that can be parsed to the
            JSON format.

        Args:
            languages (List[str]): List of languages that should be exported.
        :param languages:
        :param by_row:
        :param languages_pseudonyms:
        :return:
        """
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
        x_range = self.shape[1]
        x = self.cell_indices.columns_nicknames
        y_range = self.shape[0]
        y = self.cell_indices.rows_nicknames
        if by_row:
            x_range = self.shape[0]
            x = self.cell_indices.rows_nicknames
            y_range = self.shape[1]
            y = self.cell_indices.columns_nicknames
        # Export the spreadsheet to the dictionary (that can by JSON-ified)
        values = {}
        for idx_x in range(x_range):
            x_values = {}
            for idx_y in range(y_range):
                # Select the correct cell
                if by_row:
                    cell = self.iloc[idx_x, idx_y]
                else:
                    cell = self.iloc[idx_y, idx_x]
                # Skip if cell value is None:
                if cell.value is None:
                    continue
                parsed_cell = cell.parse
                pseudolang_and_val = {}
                for i, language in enumerate(languages):
                    pseudolang_and_val[languages_used[i]] = \
                        parsed_cell[language]
                # Append the value:
                pseudolang_and_val['value'] = cell.value
                x_values[y[idx_y]] = pseudolang_and_val
            values[x[idx_x]] = x_values
        return values

    def values_to_string(self):
        export = "["
        for row_idx in range(self.cell_indices.shape[0]):
            export += "["
            for col_idx in range(self.cell_indices.shape[1]):
                export += str(self.iloc[row_idx, col_idx].value)
                if col_idx < self.cell_indices.shape[1] - 1:
                    export += ', '
            export += "]"
            if row_idx < self.cell_indices.shape[0] - 1:
                export += ",\n"
        return export + "]"


# -----------------------------------------------------------------------------
# Some quick tests
indices = CellIndices(
    5, 6,
    rows_nicknames=['row_a', 'row_ab', 'row_ac', 'row_ad', 'row_ae'],
    columns_nicknames=['col_a', 'col_b', 'col_c', 'col_d', 'col_e', 'col_f']
)

sheet = Spreadsheet(indices)
sheet.iloc[0,0] = 7
sheet.iloc[1,0] = 8
sheet.iloc[2,0] = 9
sheet.iloc[3,0] = 10
sheet.iloc[4,0] = 11

sheet.iloc[0,1] = sheet.iloc[0,0] + sheet.iloc[1,0]

print(sheet.values_to_string())
sheet.to_excel("/home/david/Temp/excopu/excel.xlsx")
print(
    sheet.to_dictionary(
        ['native', 'excel'],
        languages_pseudonyms=['description', 'xlsx'],
        by_row=True
        )
)
