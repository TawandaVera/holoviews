from __future__ import absolute_import, division, unicode_literals

import numpy as np
import param

from ...core import util
from ...util.transform import dim
from .plot import PlotlyPlot
from ..plot import GenericElementPlot, GenericOverlayPlot
from ..util import dim_range_key
from .util import STYLE_ALIASES, get_colorscale, merge_figure


class ElementPlot(PlotlyPlot, GenericElementPlot):

    aspect = param.Parameter(default='cube', doc="""
        The aspect ratio mode of the plot. By default, a plot may
        select its own appropriate aspect ratio but sometimes it may
        be necessary to force a square aspect ratio (e.g. to display
        the plot as an element of a grid). The modes 'auto' and
        'equal' correspond to the axis modes of the same name in
        matplotlib, a numeric value may also be passed.""")

    bgcolor = param.ClassSelector(class_=(str, tuple), default=None, doc="""
        If set bgcolor overrides the background color of the axis.""")

    invert_axes = param.ObjectSelector(default=False, doc="""
        Inverts the axes of the plot. Note that this parameter may not
        always be respected by all plots but should be respected by
        adjoined plots when appropriate.""")

    invert_xaxis = param.Boolean(default=False, doc="""
        Whether to invert the plot x-axis.""")

    invert_yaxis = param.Boolean(default=False, doc="""
        Whether to invert the plot y-axis.""")

    invert_zaxis = param.Boolean(default=False, doc="""
        Whether to invert the plot z-axis.""")

    labelled = param.List(default=['x', 'y'], doc="""
        Whether to plot the 'x' and 'y' labels.""")

    logx = param.Boolean(default=False, doc="""
         Whether to apply log scaling to the x-axis of the Chart.""")

    logy  = param.Boolean(default=False, doc="""
         Whether to apply log scaling to the y-axis of the Chart.""")

    logz  = param.Boolean(default=False, doc="""
         Whether to apply log scaling to the y-axis of the Chart.""")

    margins = param.NumericTuple(default=(50, 50, 50, 50), doc="""
         Margins in pixel values specified as a tuple of the form
         (left, bottom, right, top).""")

    show_legend = param.Boolean(default=False, doc="""
        Whether to show legend for the plot.""")

    xaxis = param.ObjectSelector(default='bottom',
                                 objects=['top', 'bottom', 'bare', 'top-bare',
                                          'bottom-bare', None], doc="""
        Whether and where to display the xaxis, bare options allow suppressing
        all axis labels including ticks and xlabel. Valid options are 'top',
        'bottom', 'bare', 'top-bare' and 'bottom-bare'.""")

    xticks = param.Parameter(default=None, doc="""
        Ticks along x-axis specified as an integer, explicit list of
        tick locations, list of tuples containing the locations.""")

    yaxis = param.ObjectSelector(default='left',
                                      objects=['left', 'right', 'bare', 'left-bare',
                                               'right-bare', None], doc="""
        Whether and where to display the yaxis, bare options allow suppressing
        all axis labels including ticks and ylabel. Valid options are 'left',
        'right', 'bare' 'left-bare' and 'right-bare'.""")

    yticks = param.Parameter(default=None, doc="""
        Ticks along y-axis specified as an integer, explicit list of
        tick locations, list of tuples containing the locations.""")

    zlabel = param.String(default=None, doc="""
        An explicit override of the z-axis label, if set takes precedence
        over the dimension label.""")

    trace_kwargs = {}

    _style_key = None

    # Whether vectorized styles are applied per trace
    _per_trace = False

    # Declare which styles cannot be mapped to a non-scalar dimension
    _nonvectorized_styles = []

    def initialize_plot(self, ranges=None):
        """
        Initializes a new plot object with the last available frame.
        """
        # Get element key and ranges for frame
        fig = self.generate_plot(self.keys[-1], ranges)
        self.drawn = True
        return fig


    def generate_plot(self, key, ranges):
        element = self._get_frame(key)
        if element is None:
            return self.handles['fig']

        # Set plot options
        plot_opts = self.lookup_options(element, 'plot').options
        self.set_param(**{k: v for k, v in plot_opts.items()
                          if k in self.params()})

        # Get ranges
        ranges = self.compute_ranges(self.hmap, key, ranges)
        ranges = util.match_spec(element, ranges)

        # Get style
        self.style = self.lookup_options(element, 'style')
        style = self.style[self.cyclic_index]

        # Get data and options and merge them
        data = self.get_data(element, ranges, style)
        opts = self.graph_options(element, ranges, style)
        graphs = []
        for i, d in enumerate(data):
            # Initialize graph
            graph = self.init_graph(d, opts, index=i)
            graphs.append(graph)
        self.handles['graphs'] = graphs

        # Initialize layout
        layout = self.init_layout(key, element, ranges)
        self.handles['layout'] = layout

        # Create figure and return it
        fig = dict(data=graphs, layout=layout)
        self.handles['fig'] = fig
        return fig


    def graph_options(self, element, ranges, style):
        if self.overlay_dims:
            legend = ', '.join([d.pprint_value_string(v) for d, v in
                                self.overlay_dims.items()])
        else:
            legend = element.label

        opts = dict(
            showlegend=self.show_legend, legendgroup=element.group,
            name=legend, **self.trace_kwargs)

        if self._style_key is not None:
            styles = self._apply_transforms(element, ranges, style)
            opts[self._style_key] = {STYLE_ALIASES.get(k, k): v
                                     for k, v in styles.items()}
        else:
            opts.update({STYLE_ALIASES.get(k, k): v
                         for k, v in style.items() if k != 'cmap'})

        return opts


    def init_graph(self, data, options, index=0):
        trace = dict(options)
        for k, v in data.items():
            if k in trace and isinstance(trace[k], dict):
                trace[k].update(v)
            else:
                trace[k] = v

        if self._style_key and self._per_trace:
            vectorized = {k: v for k, v in options[self._style_key].items()
                          if isinstance(v, np.ndarray)}
            trace[self._style_key] = dict(trace[self._style_key])
            for s, val in vectorized.items():
                trace[self._style_key][s] = val[index]
        return trace


    def get_data(self, element, ranges, style):
        return []


    def get_aspect(self, xspan, yspan):
        """
        Computes the aspect ratio of the plot
        """
        return self.width/self.height


    def _get_axis_dims(self, element):
        """Returns the dimensions corresponding to each axis.

        Should return a list of dimensions or list of lists of
        dimensions, which will be formatted to label the axis
        and to link axes.
        """
        dims = element.dimensions()[:2]
        if len(dims) == 1:
            return dims + [None, None]
        else:
            return dims + [None]


    def _apply_transforms(self, element, ranges, style):
        new_style = dict(style)
        for k, v in dict(style).items():
            if isinstance(v, util.basestring):
                if v in element:
                    v = dim(v)
                elif any(d==v for d in self.overlay_dims):
                    v = dim([d for d in self.overlay_dims if d==v][0])

            if not isinstance(v, dim):
                continue
            elif (not v.applies(element) and v.dimension not in self.overlay_dims):
                new_style.pop(k)
                self.warning('Specified %s dim transform %r could not be applied, as not all '
                             'dimensions could be resolved.' % (k, v))
                continue

            if len(v.ops) == 0 and v.dimension in self.overlay_dims:
                val = self.overlay_dims[v.dimension]
            else:
                val = v.apply(element, ranges=ranges, flat=True)

            if (not util.isscalar(val) and len(util.unique_array(val)) == 1
                and not 'color' in k):
                val = val[0]

            if not util.isscalar(val):
                if k in self._nonvectorized_styles:
                    element = type(element).__name__
                    raise ValueError('Mapping a dimension to the "{style}" '
                                     'style option is not supported by the '
                                     '{element} element using the {backend} '
                                     'backend. To map the "{dim}" dimension '
                                     'to the {style} use a groupby operation '
                                     'to overlay your data along the dimension.'.format(
                                         style=k, dim=v.dimension, element=element,
                                         backend=self.renderer.backend))

            # If color is not valid colorspec add colormapper
            numeric = isinstance(val, np.ndarray) and val.dtype.kind in 'uifMm'
            if ('color' in k and isinstance(val, np.ndarray) and numeric):
                copts = self.get_color_opts(v, element, ranges, style)
                new_style.pop('cmap', None)
                new_style.update(copts)
            new_style[k] = val
        return new_style


    def init_layout(self, key, element, ranges):
        extent = self.get_extents(element, ranges)

        if len(extent) == 4:
            l, b, r, t = extent
        else:
            l, b, z0, r, t, z1 = extent

        options = {}

        dims = self._get_axis_dims(element)
        if len(dims) > 2:
            xdim, ydim, _ = dims
        else:
            xdim, ydim = dims
        xlabel, ylabel, zlabel = self._get_axis_labels(dims)

        if self.invert_axes:
            xlabel, ylabel = ylabel, xlabel
            l, b, r, t = b, l, t, r

        if 'x' not in self.labelled:
            xlabel = ''
        if 'y' not in self.labelled:
            ylabel = ''

        if xdim:
            xaxis = dict(range=[l, r], title=xlabel)
            if self.logx:
                xaxis['type'] = 'log'
            self._get_ticks(xaxis, self.xticks)
            options['xaxis'] = xaxis

        if ydim:
            yaxis = dict(range=[b, t], title=ylabel)
            if self.logy:
                yaxis['type'] = 'log'
            self._get_ticks(yaxis, self.yticks)
            options['yaxis'] = yaxis

        l, b, r, t = self.margins
        margin = dict(l=l, r=r, b=b, t=t, pad=4)
        return dict(width=self.width, height=self.height,
                    title=self._format_title(key, separator=' '),
                    plot_bgcolor=self.bgcolor, margin=margin,
                    **options)

    def _get_ticks(self, axis, ticker):
        axis_props = {}
        if isinstance(ticker, (tuple, list)):
            if all(isinstance(t, tuple) for t in ticker):
                ticks, labels = zip(*ticker)
                labels = [l if isinstance(l, util.basestring) else str(l)
                              for l in labels]
                axis_props['tickvals'] = ticks
                axis_props['ticktext'] = labels
            else:
                axis_props['tickvals'] = ticker
            axis.update(axis_props)

    def update_frame(self, key, ranges=None):
        """
        Updates an existing plot with data corresponding
        to the key.
        """
        self.generate_plot(key, ranges)


class ColorbarPlot(ElementPlot):

    colorbar = param.Boolean(default=False, doc="""
        Whether to display a colorbar.""")

    color_levels = param.ClassSelector(default=None, class_=(int, list), doc="""
        Number of discrete colors to use when colormapping or a set of color
        intervals defining the range of values to map each color to.""")

    colorbar_opts = param.Dict(default={}, doc="""
        Allows setting including borderwidth, showexponent, nticks,
        outlinecolor, thickness, bgcolor, outlinewidth, bordercolor,
        ticklen, xpad, ypad, tickangle...""")

    symmetric = param.Boolean(default=False, doc="""
        Whether to make the colormap symmetric around zero.""")

    def get_color_opts(self, eldim, element, ranges, style):
        opts = {}
        dim_name = dim_range_key(eldim)
        if self.colorbar:
            if isinstance(eldim, dim):
                title = str(eldim) if eldim.ops else str(eldim)[1:-1]
            else:
                title = eldim.pprint_label
            opts['colorbar'] = dict(title=title, **self.colorbar_opts)
        else:
            opts['showscale'] = False

        if eldim:
            auto = False
            if dim_name in ranges:
                cmin, cmax = ranges[dim_name]['combined']
            elif isinstance(eldim, dim):
                cmin, cmax = np.nan, np.nan
                auto = True
            else:
                cmin, cmax = element.range(dim_name)
            if self.symmetric:
                cabs = np.abs([cmin, cmax])
                cmin, cmax = -cabs.max(), cabs.max()
        else:
            auto = True
            cmin, cmax = None, None

        cmap = style.pop('cmap', 'viridis')
        colorscale = get_colorscale(cmap, self.color_levels, cmin, cmax)
        if cmin is not None:
            opts['cmin'] = cmin
        if cmax is not None:
            opts['cmax'] = cmax
        opts['cauto'] = auto
        opts['colorscale'] = colorscale
        return opts


class OverlayPlot(GenericOverlayPlot, ElementPlot):

    _propagate_options = [
        'width', 'height', 'xaxis', 'yaxis', 'labelled', 'bgcolor',
        'invert_axes', 'show_frame', 'show_grid', 'logx', 'logy',
        'xticks', 'toolbar', 'yticks', 'xrotation', 'yrotation',
        'invert_xaxis', 'invert_yaxis', 'sizing_mode', 'title_format',
        'padding', 'xlabel', 'ylabel', 'xlim', 'ylim', 'zlim']

    def initialize_plot(self, ranges=None):
        """
        Initializes a new plot object with the last available frame.
        """
        # Get element key and ranges for frame
        return self.generate_plot(list(self.hmap.data.keys())[0], ranges)


    def generate_plot(self, key, ranges):
        element = self._get_frame(key)

        ranges = self.compute_ranges(self.hmap, key, ranges)
        figure = None
        for okey, subplot in self.subplots.items():
            fig = subplot.generate_plot(key, ranges)
            if figure is None:
                figure = fig
            else:
                merge_figure(figure, fig)

        layout = self.init_layout(key, element, ranges)
        figure['layout'].update(layout)
        self.handles['fig'] = figure
        return figure
