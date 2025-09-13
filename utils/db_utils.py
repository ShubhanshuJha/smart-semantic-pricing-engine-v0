import psycopg2
from psycopg2 import sql, OperationalError


class DBUtil:
    def __init__(self, db_config, table_name = "PRODUCTS") -> None:
        self.db_config = db_config
        self.TABLE_NAME = table_name
        self.connection = None
        self.cursor = None
    
    def init_queries(self, CREATE_TABLE_QUERY, INSERT_DATA_QUERY):
        self.CREATE_TABLE_QUERY = CREATE_TABLE_QUERY
        self.INSERT_DATA_QUERY = INSERT_DATA_QUERY
        self.execute_query(self.CREATE_TABLE_QUERY)
    
    def preview_data(self, n=3):
        query = f"""
            SELECT * FROM {self.TABLE_NAME}
            LIMIT {n};
        """
        result = self.execute_query(query)
        print(result)
    
    def drop_table(self, mock=True):
        query = f"DROP TABLE IF EXISTS {self.TABLE_NAME};"
        if mock:
            print(f"(*) Executed query: {query}")
        else:
            self.execute_query(query)
        print(f"(*) Table {self.TABLE_NAME} dropped.")
    
    def __connect(self):
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.cursor = self.connection.cursor()
            print("(*) Connected to PostgreSQL database successfully")
        except OperationalError as ex:
            print(f"(*) Error connecting to PostgreSQL database: {ex}")
    
    def execute_query(self, query, params=None):
        """
        Executes the given SQL query.
        If fetch=True, it returns the fetched results.
        """
        try:
            if self.connection is None or self.cursor is None:
                self.__connect()
            self.cursor.execute(query, params)
            self.connection.commit()
            print("Query executed successfully")
            if self.cursor.description:
                return self.cursor.fetchall()
        except Exception as e:
            print(f"(*) Error executing query: {e}")
            self.connection.rollback()

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
            print("(*) Database connection closed")

