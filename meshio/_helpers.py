import pathlib
from typing import List, Optional

import numpy as np

from ._common import num_nodes_per_cell
from ._exceptions import ReadError, WriteError
from ._files import is_buffer
from ._mesh import CellBlock, Mesh

extension_to_filetype = {}
reader_map = {}
_writer_map = {}


def register(name: str, extensions: List[str], reader, writer_map):
    for ext in extensions:
        extension_to_filetype[ext] = name

    if reader is not None:
        reader_map[name] = reader
    _writer_map.update(writer_map)


def _filetype_from_path(path: pathlib.Path):
    ext = ""
    out = None
    for suffix in reversed(path.suffixes):
        ext = (suffix + ext).lower()
        if ext in extension_to_filetype:
            out = extension_to_filetype[ext]

    if out is None:
        raise ReadError(f"Could not deduce file format from extension '{ext}'.")
    return out


def read(filename, file_format: Optional[str] = None):
    """Reads an unstructured mesh with added data.

    :param filenames: The files/PathLikes to read from.
    :type filenames: str

    :returns mesh{2,3}d: The mesh data.
    """
    if is_buffer(filename, "r"):
        if file_format is None:
            raise ReadError("File format must be given if buffer is used")
        if file_format == "tetgen":
            raise ReadError(
                "tetgen format is spread across multiple files "
                "and so cannot be read from a buffer"
            )
        msg = f"Unknown file format '{file_format}'"
    else:
        path = pathlib.Path(filename)
        if not path.exists():
            raise ReadError(f"File {filename} not found.")

        if not file_format:
            # deduce file format from extension
            file_format = _filetype_from_path(path)

        msg = f"Unknown file format '{file_format}' of '{filename}'."

    if file_format not in reader_map:
        raise ReadError(msg)

    return reader_map[file_format](filename)


def write_points_cells(
    filename,
    points,
    cells,
    point_data=None,
    cell_data=None,
    field_data=None,
    point_sets=None,
    cell_sets=None,
    file_format=None,
    **kwargs,
):
    points = np.asarray(points)
    if isinstance(cells, dict):
        cells = [CellBlock(name, vals) for name, vals in cells.items()]
    cells = [(key, np.asarray(value)) for key, value in cells]
    mesh = Mesh(
        points,
        cells,
        point_data=point_data,
        cell_data=cell_data,
        field_data=field_data,
        point_sets=point_sets,
        cell_sets=cell_sets,
    )
    mesh.write(filename, file_format=file_format, **kwargs)


def write(filename, mesh: Mesh, file_format: Optional[str] = None, **kwargs):
    """Writes mesh together with data to a file.

    :params filename: File to write to.
    :type filename: str

    :params point_data: Named additional point data to write to the file.
    :type point_data: dict
    """
    if is_buffer(filename, "r"):
        if file_format is None:
            raise WriteError("File format must be supplied if `filename` is a buffer")
        if file_format == "tetgen":
            raise WriteError(
                "tetgen format is spread across multiple files, and so cannot be written to a buffer"
            )
    else:
        path = pathlib.Path(filename)
        if not file_format:
            # deduce file format from extension
            file_format = _filetype_from_path(path)

    try:
        writer = _writer_map[file_format]
    except KeyError:
        formats = sorted(list(_writer_map.keys()))
        raise WriteError(f"Unknown format '{file_format}'. Pick one of {formats}")

    # check cells for sanity
    for key, value in mesh.cells:
        if key[:7] == "polygon":
            try:
                n = int(key[7:])
            except ValueError:
                msg = (
                    f'Key "{key}" malformed. '
                    'Should be "polygonN", where N is the number of points per polygon.'
                )
                raise ValueError(msg)
            if value.shape[1] != n:
                raise WriteError(
                    f"Polygon data array (shape {value.shape}) "
                    f'doesn\'t match the key "{key}"'
                )
        elif key in num_nodes_per_cell:
            if value.shape[1] != num_nodes_per_cell[key]:
                raise WriteError(
                    f"Unexpected cells array shape {value.shape} for {key} cells."
                )
        else:
            # we allow custom keys <https://github.com/nschloe/meshio/issues/501> and
            # cannot check those
            pass

    # Write
    return writer(filename, mesh, **kwargs)
