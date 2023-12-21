import pandas as pd
from torch_geometric.data import Batch, HeteroData
import plotly.express as px
from plotly.graph_objects import FigureWidget
import warnings

class GraphPlot:
    def __init__(self,
                 planes: list[str],
                 classes: list[str],
                 filter_threshold: float = 0.5):
        self._planes = planes
        self._classes = classes
        self._labels = pd.CategoricalDtype(['background']+classes, ordered=True)
        self._cmap = { c: px.colors.qualitative.Plotly[i] for i, c in enumerate(classes) }
        self._cmap['background'] = 'lightgrey'
        self.filter_threshold = filter_threshold

        # temporarily silence this pandas warning triggered by plotly,
        # which we don't have any power to fix but will presumably
        # be fixed on their end at some point
        warnings.filterwarnings("ignore", ".*The default of observed=False is deprecated and will be changed to True in a future version of pandas.*")
        self._truth_cols = ( 'g4_id', 'parent_id', 'pdg' )

    def to_dataframe(self, data: HeteroData):
        def to_categorical(arr):
            return pd.Categorical.from_codes(codes=arr+1, dtype=self._labels)
        if isinstance(data, Batch):
            raise Exception('to_dataframe does not support batches!')
        dfs = []
        for p in self._planes:
            plane = data[p].to_dict()
            df = pd.DataFrame(plane['id'], columns=['id'])
            df['plane'] = p
            df[['wire','time']] = plane['pos']
            df['y_filter'] = plane['y_semantic'] != -1
            mask = df.y_filter.values
            df['y_semantic'] = to_categorical(plane['y_semantic'])
            df['y_instance'] = plane['y_instance'].numpy().astype(str)

            # add detailed truth information if it's available
            for col in self._truth_cols:
                if col in plane.keys():
                    df[col] = plane[col].numpy()

            # add model prediction if it's available
            if 'x_semantic' in plane.keys():
                df['x_semantic'] = to_categorical(plane['x_semantic'].argmax(dim=-1).detach())
                df[self._classes] = plane['x_semantic'].detach()
            if 'x_filter' in plane.keys():
                df['x_filter'] = plane['x_filter'].detach()

            dfs.append(df)
        df = pd.concat(dfs)
        md = data['metadata']
        df['run'] = md.run.item()
        df['subrun'] = md.subrun.item()
        df['event'] = md.event.item()
        return df

    def plot(self,
             data: HeteroData,
             target: str = 'hits',
             how: str = 'none',
             filter: str = 'show',
             width: int = None,
             height: int = None) -> FigureWidget:

        df = self.to_dataframe(data)

        # no colour
        if target == 'hits':
            opts = {
                'title': 'Graph hits',
            }

        # semantic labels
        elif target == 'semantic':
            if how == 'true':
                opts = {
                    'title': 'True semantic labels',
                    'labels': { 'y_semantic': 'Semantic label' },
                    'color': 'y_semantic',
                    'color_discrete_map': self._cmap,
                }
            elif how == 'pred':
                opts = {
                    'title': 'Predicted semantic labels',
                    'labels': { 'x_semantic': 'Semantic label' },
                    'color': 'x_semantic',
                    'color_discrete_map': self._cmap,
                }
            elif how in self._classes:
                opts = {
                    'title': f'Predicted semantic label strength for {how} class',
                    'labels': { how: f'{how} probability' },
                    'color': how,
                    'color_continuous_scale': px.colors.sequential.Reds,
                }
            else:
                raise Exception('for semantic labels, "how" must be one of "true", "pred" or the name of a class.')

        # instance labels
        elif target == 'instance':
            if how == 'true':
                opts = {
                    'title': 'True instance labels',
                    'labels': { 'y_instance': 'Instance label' },
                    'color': 'y_instance',
                    'symbol': 'y_semantic',
                    'color_discrete_map': self._cmap,
                }
            elif how == 'pred':
                opts = {
                    'title': 'Predicted instance labels',
                    'labels': { 'x_instance': 'Instance label' },
                    'color': 'x_instance',
                    'symbol': 'x_semantic',
                    'color_discrete_map': self._cmap,
                }
            else:
                raise Exception('for instance labels, "how" must be one of "true" or "pred".')

        # filter labels
        elif target == 'filter':
            if how == 'true':
                opts = {
                    'title': 'True filter labels',
                    'labels': { 'y_filter': 'Filter label' },
                    'color': 'y_filter',
                    'color_discrete_map': { 0: 'coral', 1: 'mediumseagreen' },
                }
            elif how == 'pred':
                opts = {
                    'title': 'Predicted filter labels',
                    'labels': { 'x_filter': 'Filter label' },
                    'color': 'x_filter',
                    'color_continuous_scale': px.colors.sequential.Reds,
                }
            else:
                raise Exception('for filter labels, "how" must be one of "true" or "pred".')

        else:
            raise Exception('"target" must be one of "hits", "semantic", "instance" or "filter".')

        if filter == 'none':
            # don't do any filtering
            pass
        elif filter == 'show':
            # show hits predicted to be background in grey
            if target == 'semantic' and how == 'pred':
                df.x_semantic[df.x_filter < self.filter_threshold] = 'background'
        elif filter == 'true':
            # remove true background hits
            df = df[df.y_filter.values]
            opts['title'] += ' (filtered by truth)'
        elif filter == 'pred':
            # remove predicted background hits
            df = df[df.x_filter > self.filter_threshold]
            opts['title'] += ' (filtered by prediction)'
        else:
            raise Exception('"filter" must be one of "none", "show", "true" or "pred".')

        # set hover data
        opts['hover_data'] = {
            'y_semantic': True,
            'wire': ':.1f',
            'time': ':.1f',
        }
        opts['labels'] = {
            'y_filter': 'filter truth',
            'y_semantic': 'semantic truth',
            'y_instance': 'instance truth',
        }
        if 'x_filter' in df:
            opts['hover_data']['x_filter'] = True
            opts['labels']['x_filter'] = 'filter prediction'
        if 'x_semantic' in df:
            opts['hover_data']['x_semantic'] = True
            opts['labels']['x_semantic'] = 'semantic prediction'
        if 'x_instance' in df:
            opts['hover_data']['x_instance'] = ':.4f'
            opts['labels']['x_instance'] = 'instance prediction'
        for col in self._truth_cols:
            if col in df:
                opts['hover_data'][col] = True

        fig = px.scatter(df, x='wire', y='time', facet_col='plane',
                         width=width, height=height, **opts)
        fig.update_xaxes(matches=None)
        for a in fig.layout.annotations:
            a.text = a.text.replace('plane=', '')
        return FigureWidget(fig)