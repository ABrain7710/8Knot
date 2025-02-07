import logging
from db_manager.augur_manager import AugurManager
from app import celery_app
import pandas as pd
from cache_manager.cache_manager import CacheManager as cm
import io

QUERY_NAME = "COMPANY"


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    exponential_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def company_query(self, dbmc, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for company affiliation data.

    Args:
    -----
        dbmc (AugurManager): Handles connection to Augur database, executes queries and returns results.

        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.debug(f"{QUERY_NAME}_DATA_QUERY - START")

    if len(repos) == 0:
        return None

    query_string = f"""
                    SELECT
                        c.cntrb_id,
                        c.created_at AS created,
                        c.repo_id AS id,
                        c.login,
                        c.action,
                        c.rank,
                        con.cntrb_company,
                        string_agg(ca.alias_email, ' , ' order by ca.alias_email) as email_list
                    FROM
                        explorer_contributor_actions c
                    JOIN contributors_aliases ca
                        ON c.cntrb_id = ca.cntrb_id
                    JOIN contributors con
                        ON c.cntrb_id = con.cntrb_id
                    WHERE
                        c.repo_id in({str(repos)[1:-1]})
                    GROUP BY c.cntrb_id, c.created_at, c.repo_id, c.login, c.action, c.rank, con.cntrb_company
                    """
    # create database connection, load config, execute query above.
    dbm = AugurManager()
    dbm.load_pconfig(dbmc)
    df = dbm.run_query(query_string)

    df["cntrb_id"] = df["cntrb_id"].astype(str)
    df = df.sort_values(by="created")
    df = df.reset_index()
    df.drop("index", axis=1, inplace=True)

    # break apart returned data per repo
    # and temporarily store in List to be
    # stored in Redis.
    pic = []
    for r in repos:
        # convert series to a dataframe
        # once we've stored the data by ID we no longer need the column.
        c_df = pd.DataFrame(df.loc[df["id"] == r].drop(columns=["id"])).reset_index(drop=True)

        # bytes buffer to be written to
        b = io.BytesIO()

        # write dataframe in feather format to BytesIO buffer
        bs = c_df.to_feather(b)

        # move head of buffer to the beginning
        b.seek(0)

        # write the bytes of the buffer into the array
        bs = b.read()
        pic.append(bs)

    del df

    # store results in Redis
    cm_o = cm()

    # 'ack' is a boolean of whether data was set correctly or not.
    ack = cm_o.setm(
        func=company_query,
        repos=repos,
        datas=pic,
    )

    logging.debug(f"{QUERY_NAME}_DATA_QUERY - END")
    return ack
