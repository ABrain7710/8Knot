from dash import html, dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import color_seq
from queries.company_query import company_query as cmq
import io
from cache_manager.cache_manager import CacheManager as cm
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt

PAGE = "company"
VIZ_ID = "unique-domains"

gc_unique_domains = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H3(
                    "Unique Contributor Email Domains",
                    className="card-title",
                    style={"textAlign": "center"},
                ),
                dbc.Popover(
                    [
                        dbc.PopoverHeader("Graph Info:"),
                        dbc.PopoverBody("This graph counts the number of UNIQUE emails by domains"),
                    ],
                    id=f"popover-{PAGE}-{VIZ_ID}",
                    target=f"popover-target-{PAGE}-{VIZ_ID}",  # needs to be the same as dbc.Button id
                    placement="top",
                    is_open=False,
                ),
                dcc.Loading(
                    dcc.Graph(id=f"{PAGE}-{VIZ_ID}"),
                ),
                dbc.Form(
                    [
                        dbc.Row(
                            [
                                dbc.Label(
                                    "Contributors Required:",
                                    html_for=f"contributions-required-{PAGE}-{VIZ_ID}",
                                    width={"size": "auto"},
                                ),
                                dbc.Col(
                                    dbc.Input(
                                        id=f"contributions-required-{PAGE}-{VIZ_ID}",
                                        type="number",
                                        min=1,
                                        max=50,
                                        step=1,
                                        value=3,
                                        size="sm",
                                    ),
                                    className="me-2",
                                    width=2,
                                ),
                            ],
                            align="center",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dcc.DatePickerRange(
                                        id=f"date-picker-range-{PAGE}-{VIZ_ID}",
                                        min_date_allowed=dt.date(2005, 1, 1),
                                        max_date_allowed=dt.date.today(),
                                        clearable=True,
                                    ),
                                    width="auto",
                                ),
                                dbc.Col(
                                    dbc.Button(
                                        "About Graph",
                                        id=f"popover-target-{PAGE}-{VIZ_ID}",
                                        color="secondary",
                                        size="sm",
                                    ),
                                    width="auto",
                                    style={"paddingTop": ".5em"},
                                ),
                            ],
                            align="center",
                            justify="between",
                        ),
                    ]
                ),
            ]
        )
    ],
)

# callback for graph info popover
@callback(
    Output(f"popover-{PAGE}-{VIZ_ID}", "is_open"),
    [Input(f"popover-target-{PAGE}-{VIZ_ID}", "n_clicks")],
    [State(f"popover-{PAGE}-{VIZ_ID}", "is_open")],
)
def toggle_popover(n, is_open):
    if n:
        return not is_open
    return is_open


# callback for Company Affiliation by Github Account Info graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"contributions-required-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
    ],
    background=True,
)
def unique_domains_graph(repolist, num, start_date, end_date):

    # wait for data to asynchronously download and become available.
    cache = cm()
    df = cache.grabm(func=cmq, repos=repolist)
    while df is None:
        time.sleep(1.0)
        df = cache.grabm(func=cmq, repos=repolist)

    start = time.perf_counter()
    logging.debug(f"{VIZ_ID}- START")

    # test if there is data
    if df.empty:
        logging.debug(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing, COULD HAVE ADDITIONAL INPUTS AND OUTPUTS
    df = process_data(df, num, start_date, end_date)

    fig = create_figure(df)

    logging.debug(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, num, start_date, end_date):

    # convert to datetime objects rather than strings
    df["created"] = pd.to_datetime(df["created"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created >= start_date]
    if end_date is not None:
        df = df[df.created <= end_date]

    # creates list of unique emails and flattens list result
    emails = df.email_list.str.split(" , ").explode("email_list").unique().tolist()

    # remove any entries not in email format
    emails = [x for x in emails if "@" in x]

    # creates list of email domains from the emails list
    email_domains = [x[x.rindex("@") + 1 :] for x in emails]

    # creates df of domains and counts
    df = pd.DataFrame(email_domains, columns=["domains"]).value_counts().to_frame().reset_index()

    df = df.rename(columns={0: "occurences"})

    # changes the name of the company if under a certain threshold
    df.loc[df.occurences <= num, "domains"] = "Other"

    # groups others together for final counts
    df = (
        df.groupby(by="domains")["occurences"]
        .sum()
        .reset_index()
        .sort_values(by=["occurences"], ascending=False)
        .reset_index(drop=True)
    )

    return df


def create_figure(df: pd.DataFrame):

    # graph generation
    fig = px.pie(df, names="domains", values="occurences", color_discrete_sequence=color_seq)
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label} <br>Contributions: %{value}<br><extra></extra>",
    )

    return fig
