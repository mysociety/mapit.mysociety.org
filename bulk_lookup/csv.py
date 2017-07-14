import os
import mmap
import pyexcel
from pyexcel._compact import zip_longest
import defusedxml

defusedxml.defuse_stdlib()


class file_without_nulls_or_cp1252(object):
    """An object that behaves like a provided file object,
    but strips any NULL bytes when read() is called, and
    spots Windows-1252 lines."""
    def __init__(self, f):
        object.__setattr__(self, '_file', f)

    def __getattr__(self, name):
        return getattr(self._file, name)

    def __setattr__(self, name, value):
        return setattr(self._file, name, value)

    def whole_character(self, data):
        if '\xc2' <= data[-1] <= '\xdf' or (len(data) > 1 and '\xe0' <= data[-2] <= '\xef'):
            return self._file.read(1)
        if '\xe0' <= data[-1] <= '\xef' or (len(data) > 1 and '\xf0' <= data[-2] <= '\xf4'):
            return self._file.read(2)
        if '\xf0' <= data[-1] <= '\xf4':
            return self._file.read(3)
        if len(data) > 2 and '\xf0' <= data[-3] <= '\xf4':
            return self._file.read(1)
        return ''

    def read(self, *args):
        # Remove null bytes from any underlying data
        data = self._file.read(*args)
        if data:
            data += self.whole_character(data)
        data = data.replace('\0', '')
        try:
            # If it's not UTF-8...
            data.decode('utf-8')
        except UnicodeDecodeError:
            # ...Assume Windows 1252
            data = data.decode('cp1252').encode('utf-8')
        return data


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
        elif ext == 'csv':
            kwargs['file_stream'] = file_without_nulls_or_cp1252(file_field)
        else:  # ODS
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
