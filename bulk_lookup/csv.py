import os
import mmap
import pyexcel
from pyexcel._compact import zip_longest
import defusedxml

defusedxml.defuse_stdlib()


class PyExcelReader(object):
    # Set up an iterator for reading in a CSV/XLS/XLSX/ODS file
    def __init__(self, file_field):
        self._fieldnames = None
        root, ext = os.path.splitext(file_field.name)
        ext = ext[1:] or 'csv'
        kwargs = {'file_type': ext, 'sheet_index': 0}
        file_field.open()  # Might have already been read once
        # The XLS reader doesn't accept a stream, but does accept an mmap file...
        if ext in ('xls', 'xlsx'):
            kwargs['file_content'] = mmap.mmap(file_field.fileno(), 0, access=mmap.ACCESS_READ)
        else:  # CSV or ODS
            kwargs['file_stream'] = file_field
        self.reader = self.iget_records(**kwargs)

    # Similar to pyexcel.core's, in order to be able to store the header row
    def iget_records(self, **keywords):
        sheet_stream = pyexcel.sources.get_sheet_stream(**keywords)
        return sheet_stream.payload  # This will be a generator

    # Very similar to what csv does
    @property
    def fieldnames(self):
        if self._fieldnames is None:
            try:
                self._fieldnames = self.reader.next()
            except StopIteration:
                pass
        return self._fieldnames

    @fieldnames.setter
    def fieldnames(self, value):
        self._fieldnames = value

    # Smaller version of csv DictReader's
    def next(self):
        self.fieldnames  # for the side effect
        row = self.reader.next()
        while row == []:
            row = self.reader.next()
        return dict(zip_longest(self.fieldnames, row, fillvalue=''))

    def __iter__(self):
        return self
