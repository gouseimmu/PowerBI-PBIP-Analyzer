"""Test fixtures and mock PBIP archive generators for automated testing."""

import os
import json
import zipfile


def create_mock_tmdl_pbip_zip(output_path: str) -> str:
    """Generate a realistic mock PBIP ZIP containing TMDL semantic model, multi-level DAX dependencies, and PBIR report."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Project file
        pbip_content = json.dumps({
            "version": "1.0",
            "artifacts": [
                {"type": "Report", "path": "SalesAnalytics.Report"},
                {"type": "SemanticModel", "path": "SalesAnalytics.SemanticModel"}
            ],
            "settings": {}
        }, indent=2)
        zf.writestr("SalesAnalytics.pbip", pbip_content)

        # 2. Semantic Model pbism and TMDL files
        zf.writestr("SalesAnalytics.SemanticModel/definition.pbism", json.dumps({"version": "1.0"}))
        
        # model.tmdl
        model_tmdl = """model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US

\tannotation __PBI_TimeIntelligenceEnabled = 1
"""
        zf.writestr("SalesAnalytics.SemanticModel/definition/model.tmdl", model_tmdl)

        # tables/Customer.tmdl
        customer_tmdl = """table Customer
\tlineageTag: 11111111-2222-3333-4444-555555555555

\tcolumn CustomerKey
\t\tdataType: int64
\t\tformatString: 0
\t\tsourceColumn: CustomerKey

\tcolumn 'Customer Name'
\t\tdataType: string
\t\tsourceColumn: CustomerName

\tcolumn FirstName
\t\tdataType: string
\t\tsourceColumn: FirstName

\tcolumn LastName
\t\tdataType: string
\t\tsourceColumn: LastName

\tcolumn 'Full Name' = [FirstName] & " " & [LastName]
\t\tdataType: string

\tmeasure 'Customer Count' = DISTINCTCOUNT(Customer[CustomerKey])
\t\tformatString: #,##0
\t\tdescription: "Total distinct customer count"

\tpartition Customer = m
\t\tmode: import
\t\tsource =
\t\t\tlet
\t\t\t\tSource = Sql.Database("sql-server.database.windows.net", "SalesDW"),
\t\t\t\tCustomers = Source{[Schema="dbo",Item="DimCustomer"]}[Data]
\t\t\tin
\t\t\t\tCustomers
"""
        zf.writestr("SalesAnalytics.SemanticModel/definition/tables/Customer.tmdl", customer_tmdl)

        # tables/Sales.tmdl
        sales_tmdl = """table Sales
\tlineageTag: 66666666-7777-8888-9999-000000000000

\tcolumn SalesKey
\t\tdataType: int64
\t\tsourceColumn: SalesKey

\tcolumn CustomerKey
\t\tdataType: int64
\t\tsourceColumn: CustomerKey

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tsourceColumn: OrderDate

\tcolumn Amount
\t\tdataType: decimal
\t\tformatString: $#,##0.00
\t\tsourceColumn: Amount

\tcolumn Cost
\t\tdataType: decimal
\t\tformatString: $#,##0.00
\t\tsourceColumn: Cost

\tcolumn 'Margin Percent' = ```
\t\tDIVIDE(Sales[Amount] - Sales[Cost], Sales[Amount], 0)
\t\t```
\t\tdataType: double
\t\tformatString: 0.0%

\tcolumn 'Unused Calc Column' = Sales[Amount] * 0.05
\t\tdataType: double

\tmeasure 'Total Sales' = ```
\t\tVAR Total = SUM(Sales[Amount])
\t\tRETURN Total
\t\t```
\t\tformatString: $#,##0.00
\t\tdescription: "Sum of sales revenue"

\tmeasure 'Total Margin' = SUM(Sales[Amount]) - SUM(Sales[Cost])
\t\tformatString: $#,##0.00

\tmeasure 'Sales YTD' = TOTALYTD([Total Sales], 'Date'[Date])
\t\tformatString: $#,##0.00

\tmeasure 'Sales Growth' = DIVIDE([Sales YTD] - [Total Sales], [Total Sales], 0)
\t\tformatString: 0.0%

\tmeasure 'Unused Old Measure' = AVERAGE(Sales[Amount]) * 10
\t\tformatString: #,##0

\tpartition Sales = m
\t\tmode: import
\t\tsource =
\t\t\tlet
\t\t\t\tSource = Excel.Workbook(File.Contents("C:\\Data\\Sales2026.xlsx")),
\t\t\t\tSales_Sheet = Source{[Item="Sheet1",Kind="Sheet"]}[Data]
\t\t\tin
\t\t\t\tSales_Sheet
"""
        zf.writestr("SalesAnalytics.SemanticModel/definition/tables/Sales.tmdl", sales_tmdl)

        # tables/Date.tmdl (Explicit Date Table)
        date_tmdl = """table Date
\tlineageTag: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
\tdataCategory: Time

\tcolumn Date
\t\tdataType: dateTime
\t\tisKey
\t\tformatString: yyyy-mm-dd
\t\tsourceColumn: Date

\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: string
\t\tsourceColumn: Month

\tpartition Date = calculated
\t\tmode: import
\t\tsource = CALENDAR(DATE(2020,1,1), DATE(2030,12,31))
"""
        zf.writestr("SalesAnalytics.SemanticModel/definition/tables/Date.tmdl", date_tmdl)

        # relationships.tmdl
        rel_tmdl = """relationship rel-sales-customer
\tfromColumn: Sales.CustomerKey
\ttoColumn: Customer.CustomerKey
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-sales-date
\tfromColumn: Sales.OrderDate
\ttoColumn: Date.Date
\tcardinality: manyToOne
\tcrossFilteringBehavior: bothDirections
\tisActive: false
"""
        zf.writestr("SalesAnalytics.SemanticModel/definition/relationships.tmdl", rel_tmdl)

        # 3. Report definition (Modern PBIR)
        zf.writestr("SalesAnalytics.Report/definition.pbir", json.dumps({"version": "1.0"}))
        
        # Page 1: Overview
        p1_json = {
            "name": "ReportSectionOverview",
            "displayName": "Executive Overview",
            "displayOption": "FitToPage"
        }
        zf.writestr("SalesAnalytics.Report/definition/pages/ReportSectionOverview/page.json", json.dumps(p1_json))

        # Visual 1 on Page 1 (Uses [Sales Growth] -> which depends on [Sales YTD], [Total Sales], Sales[Amount], Date[Date])
        v1_json = {
            "name": "vis_kpi_sales",
            "visual": {
                "visualType": "card",
                "query": {
                    "queryState": {
                        "Values": {
                            "projections": [
                                {
                                    "field": {
                                        "Measure": {
                                            "Expression": {"SourceRef": {"Entity": "Sales"}},
                                            "Property": "Sales Growth"
                                        }
                                    },
                                    "queryRef": "Sales.Sales Growth"
                                }
                            ]
                        }
                    }
                },
                "visualContainerObjects": {
                    "title": [{
                        "properties": {
                            "text": {
                                "expr": {
                                    "Literal": {
                                        "Value": "'Total Revenue KPI'"
                                    }
                                }
                            }
                        }
                    }]
                }
            }
        }
        zf.writestr("SalesAnalytics.Report/definition/pages/ReportSectionOverview/visuals/vis_kpi_sales/visual.json", json.dumps(v1_json))

        # Visual 2 on Page 1 (Directly uses Sales[Amount] and Date[Date])
        v2_json = {
            "name": "vis_sales_by_month",
            "visual": {
                "visualType": "lineChart",
                "query": {
                    "queryState": {
                        "Category": {
                            "projections": [
                                {
                                    "field": {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Entity": "Date"}},
                                            "Property": "Date"
                                        }
                                    },
                                    "queryRef": "Date.Date"
                                }
                            ]
                        },
                        "Y": {
                            "projections": [
                                {
                                    "field": {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Entity": "Sales"}},
                                            "Property": "Amount"
                                        }
                                    },
                                    "queryRef": "Sales.Amount"
                                }
                            ]
                        }
                    }
                },
                "visualContainerObjects": {
                    "title": [{
                        "properties": {
                            "text": {
                                "expr": {
                                    "Literal": {
                                        "Value": "'Monthly Revenue Trend'"
                                    }
                                }
                            }
                        }
                    }]
                }
            }
        }
        zf.writestr("SalesAnalytics.Report/definition/pages/ReportSectionOverview/visuals/vis_sales_by_month/visual.json", json.dumps(v2_json))

        # Page 2: Customer Detail
        p2_json = {
            "name": "ReportSectionCustomer",
            "displayName": "Customer Analysis",
            "displayOption": "FitToPage"
        }
        zf.writestr("SalesAnalytics.Report/definition/pages/ReportSectionCustomer/page.json", json.dumps(p2_json))

        # Visual 3 on Page 2 (Uses Customer[Customer Name] and [Customer Count])
        v3_json = {
            "name": "vis_cust_table",
            "visual": {
                "visualType": "tableEx",
                "title": "Customer Breakdown",
                "query": {
                    "queryState": {
                        "Values": {
                            "projections": [
                                {
                                    "field": {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Entity": "Customer"}},
                                            "Property": "Customer Name"
                                        }
                                    },
                                    "queryRef": "Customer.Customer Name"
                                },
                                {
                                    "field": {
                                        "Measure": {
                                            "Expression": {"SourceRef": {"Entity": "Customer"}},
                                            "Property": "Customer Count"
                                        }
                                    },
                                    "queryRef": "Customer.Customer Count"
                                }
                            ]
                        }
                    }
                }
            }
        }
        zf.writestr("SalesAnalytics.Report/definition/pages/ReportSectionCustomer/visuals/vis_cust_table/visual.json", json.dumps(v3_json))

    return output_path


def create_mock_bim_pbip_zip(output_path: str) -> str:
    """Generate a mock PBIP ZIP containing model.bim JSON semantic model."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("FinanceReport.pbip", json.dumps({"version": "1.0"}))
        zf.writestr("FinanceReport.SemanticModel/definition.pbism", "{}")

        model_bim = {
            "name": "FinanceModel",
            "compatibilityLevel": 1550,
            "model": {
                "culture": "en-US",
                "tables": [
                    {
                        "name": "Transactions",
                        "isHidden": False,
                        "columns": [
                            {"name": "TxnID", "dataType": "int64", "sourceColumn": "TxnID"},
                            {"name": "AccountID", "dataType": "int64", "sourceColumn": "AccountID"},
                            {"name": "Amount", "dataType": "decimal", "sourceColumn": "Amount"},
                            {
                                "name": "IsCredit",
                                "type": "calculated",
                                "dataType": "boolean",
                                "expression": "IF(Transactions[Amount] > 0, TRUE, FALSE)"
                            }
                        ],
                        "measures": [
                            {
                                "name": "Net Balance",
                                "expression": "SUM(Transactions[Amount])",
                                "formatString": "$#,##0.00",
                                "description": "Net sum of transaction amounts"
                            }
                        ],
                        "partitions": [
                            {
                                "name": "Transactions",
                                "source": {
                                    "type": "m",
                                    "expression": 'let Source = SharePoint.Files("https://company.sharepoint.com/finance") in Source'
                                }
                            }
                        ]
                    },
                    {
                        "name": "Accounts",
                        "columns": [
                            {"name": "AccountID", "dataType": "int64", "sourceColumn": "AccountID"},
                            {"name": "AccountName", "dataType": "string", "sourceColumn": "AccountName"}
                        ],
                        "partitions": [
                            {
                                "name": "Accounts",
                                "source": {
                                    "type": "m",
                                    "expression": 'let Source = Csv.Document(File.Contents("C:\\Data\\Accounts.csv")) in Source'
                                }
                            }
                        ]
                    }
                ],
                "relationships": [
                    {
                        "fromTable": "Transactions",
                        "fromColumn": "AccountID",
                        "toTable": "Accounts",
                        "toColumn": "AccountID",
                        "cardinality": "manyToOne",
                        "crossFilteringBehavior": "oneDirection",
                        "isActive": True
                    }
                ]
            }
        }
        zf.writestr("FinanceReport.SemanticModel/model.bim", json.dumps(model_bim, indent=2))

        # Report definition with report.json
        report_json = {
            "sections": [
                {
                    "name": "Section1",
                    "displayName": "Finance Summary",
                    "visualContainers": [
                        {
                            "id": 101,
                            "config": json.dumps({
                                "name": "card_balance",
                                "singleVisual": {
                                    "visualType": "card",
                                    "projections": {
                                        "Values": [
                                            {"queryRef": "Transactions.Net Balance"}
                                        ]
                                    },
                                    "vcObjects": {
                                        "title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Total Balance'"}}}}}]
                                    }
                                }
                            })
                        }
                    ]
                }
            ]
        }
        zf.writestr("FinanceReport.Report/report.json", json.dumps(report_json, indent=2))

    return output_path


def create_mock_workforce_pbip_zip(output_path: str) -> str:
    """Generate a realistic PBIP ZIP modeling the user's workforce report with SQL Server TMDL, multiline DAX, and system date tables."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("WorkforceAnalytics.pbip", json.dumps({
            "version": "1.0",
            "artifacts": [
                {"type": "Report", "path": "WorkforceAnalytics.Report"},
                {"type": "SemanticModel", "path": "WorkforceAnalytics.SemanticModel"}
            ]
        }))

        zf.writestr("WorkforceAnalytics.SemanticModel/definition.pbism", json.dumps({"version": "1.0"}))
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/model.tmdl", "model Model\n\tculture: en-US\n")

        # 1. User Tables (12 tables + 1 helper table)
        # Calendar (Marked Date Table)
        calendar_tmdl = """table Calendar
\tdataCategory: Time

\tcolumn CalendarDate
\t\tdataType: dateTime
\t\tisKey
\t\tformatString: yyyy-mm-dd
\t\tsourceColumn: CalendarDate

\t\tvariation Variation
\t\t\tisDefault
\t\t\trelationship: rel-cal-var
\t\t\tdefaultHierarchy: LocalDateTable_a1b2c3d4.'[Date Hierarchy]'

\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: string
\t\tsourceColumn: Month

\tpartition Calendar = calculated
\t\tmode: import
\t\tsource = CALENDAR(DATE(2020,1,1), DATE(2030,12,31))
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Calendar.tmdl", calendar_tmdl)

        # _Measures (Helper Table)
        measures_table_tmdl = """table _Measures
\tlineageTag: 99999999-0000-1111-2222-333333333333
\tcolumn _dummy
\t\tdataType: string
\t\tisHidden
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/_Measures.tmdl", measures_table_tmdl)

        # Employee (with self-referencing relationship, calculated columns)
        employee_tmdl = """table Employee
\tcolumn EmployeeID
\t\tdataType: int64
\t\tsourceColumn: EmployeeID

\tcolumn ManagerID
\t\tdataType: int64
\t\tsourceColumn: ManagerID

\tcolumn DepartmentID
\t\tdataType: int64
\t\tsourceColumn: DepartmentID

\tcolumn EmployeeName
\t\tdataType: string
\t\tsourceColumn: EmployeeName

\tcolumn HireDate
\t\tdataType: dateTime
\t\tsourceColumn: HireDate

\tcolumn 'Employee Tenure' =
\t\tDATEDIFF(
\t\t\tEmployee[HireDate],
\t\t\tTODAY(),
\t\t\tYEAR
\t\t)
\t\tdataType: int64

\tcolumn 'Employee Level' = IF(Employee[Employee Tenure] > 5, "Senior", "Junior")
\t\tdataType: string

\tpartition Employee = m
\t\tmode: import
\t\tsource =
\t\t\tlet
\t\t\t\tSource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW"),
\t\t\t\tEmp = Source{[Schema="dbo",Item="Employee"]}[Data]
\t\t\tin
\t\t\t\tEmp
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Employee.tmdl", employee_tmdl)

        # Department
        dept_tmdl = """table Department
\tcolumn DepartmentID
\t\tdataType: int64
\t\tsourceColumn: DepartmentID

\tcolumn DepartmentName
\t\tdataType: string
\t\tsourceColumn: DepartmentName

\tpartition Department = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Department.tmdl", dept_tmdl)

        # Project
        project_tmdl = """table Project
\tcolumn ProjectID
\t\tdataType: int64
\t\tsourceColumn: ProjectID

\tcolumn ProjectName
\t\tdataType: string
\t\tsourceColumn: ProjectName

\tcolumn StartDate
\t\tdataType: dateTime
\t\tsourceColumn: StartDate

\tcolumn EndDate
\t\tdataType: dateTime
\t\tsourceColumn: EndDate

\tmeasure 'Project Start Count' =
\t\tCALCULATE(
\t\t\tCOUNTROWS(Project),
\t\t\tUSERELATIONSHIP(
\t\t\t\tCalendar[CalendarDate],
\t\t\t\tProject[StartDate]
\t\t\t)
\t\t)
\t\tformatString: #,##0

\tmeasure 'Project End Count' =
\t\tCALCULATE(
\t\t\tCOUNTROWS(Project),
\t\t\tUSERELATIONSHIP(
\t\t\t\tCalendar[CalendarDate],
\t\t\t\tProject[EndDate]
\t\t\t)
\t\t)
\t\tformatString: #,##0

\tpartition Project = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Project.tmdl", project_tmdl)

        # EmployeeProject (Bridge table)
        emp_proj_tmdl = """table EmployeeProject
\tcolumn EmployeeID
\t\tdataType: int64
\t\tsourceColumn: EmployeeID

\tcolumn ProjectID
\t\tdataType: int64
\t\tsourceColumn: ProjectID

\tpartition EmployeeProject = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/EmployeeProject.tmdl", emp_proj_tmdl)

        # Timesheet
        timesheet_tmdl = """table Timesheet
\tcolumn TimesheetID
\t\tdataType: int64
\t\tsourceColumn: TimesheetID

\tcolumn EmployeeID
\t\tdataType: int64
\t\tsourceColumn: EmployeeID

\tcolumn Date
\t\tdataType: dateTime
\t\tsourceColumn: Date

\tcolumn HoursWorked
\t\tdataType: decimal
\t\tsourceColumn: HoursWorked

\tcolumn BillableHours
\t\tdataType: decimal
\t\tsourceColumn: BillableHours

\tcolumn OvertimeHours
\t\tdataType: decimal
\t\tsourceColumn: OvertimeHours

\tmeasure 'Total Hours' = SUM(Timesheet[HoursWorked])
\t\tformatString: #,##0.0

\tmeasure 'Billable Hours' = SUM(Timesheet[BillableHours])
\t\tformatString: #,##0.0

\tmeasure 'Overtime Hours' = SUM(Timesheet[OvertimeHours])
\t\tformatString: #,##0.0

\tmeasure 'Billable %' =
\t\tDIVIDE(
\t\t\t[Billable Hours],
\t\t\t[Total Hours]
\t\t)
\t\tformatString: 0.0%

\tmeasure 'Adjusted Hours' =
\t\tSUMX(
\t\t\tTimesheet,
\t\t\tTimesheet[HoursWorked] - Timesheet[OvertimeHours]
\t\t)

\tmeasure 'High Billable Hours' =
\t\tCALCULATE(
\t\t\t[Billable Hours],
\t\t\tFILTER(
\t\t\t\tTimesheet,
\t\t\t\tTimesheet[BillableHours] > 5
\t\t\t)
\t\t)

\tmeasure 'Profitability Indicator' =
\t\tVAR Total =
\t\t\t[Total Hours]
\t\tVAR Billable =
\t\t\t[Billable Hours]
\t\tVAR Ratio =
\t\t\tDIVIDE(
\t\t\t\tBillable,
\t\t\t\tTotal
\t\t\t)
\t\tRETURN
\t\t\tIF(
\t\t\t\tRatio >= 0.8,
\t\t\t\t"High",
\t\t\t\t"Low"
\t\t\t)

\tcolumn 'Unsafe Margin' =
\t\t[Total Employee Cost] / [Total Hours]
\t\tdataType: double

\tcolumn 'Repeated Calculation' =
\t\tIF(
\t\t\t[Total Hours] > 100,
\t\t\tDIVIDE(
\t\t\t\t[Billable Hours],
\t\t\t\t[Total Hours]
\t\t\t),
\t\t\tDIVIDE(
\t\t\t\t[Billable Hours],
\t\t\t\t[Total Hours]
\t\t\t)
\t\t)
\t\tdataType: double

\tpartition Timesheet = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Timesheet.tmdl", timesheet_tmdl)

        # Payroll
        payroll_tmdl = """table Payroll
\tcolumn PayrollID
\t\tdataType: int64
\t\tsourceColumn: PayrollID

\tcolumn EmployeeID
\t\tdataType: int64
\t\tsourceColumn: EmployeeID

\tcolumn GrossPay
\t\tdataType: decimal
\t\tsourceColumn: GrossPay

\tmeasure 'Total Employee Cost' = SUM(Payroll[GrossPay])
\t\tformatString: $#,##0

\tmeasure 'Average Employee Cost' = AVERAGE(Payroll[GrossPay])
\t\tformatString: $#,##0

\tmeasure 'Cost Per Billable Hour' =
\t\tDIVIDE(
\t\t\t[Total Employee Cost],
\t\t\t[Billable Hours]
\t\t)

\tmeasure 'Safe Margin' = DIVIDE([Total Employee Cost], [Total Hours], 0)

\tpartition Payroll = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Payroll.tmdl", payroll_tmdl)

        # Training (contains unused measure)
        training_tmdl = """table Training
\tcolumn TrainingID
\t\tdataType: int64
\t\tsourceColumn: TrainingID

\tcolumn TrainingName
\t\tdataType: string
\t\tsourceColumn: TrainingName

\tmeasure 'Unused Training Count' = COUNTROWS(Training)

\tpartition Training = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/Training.tmdl", training_tmdl)

        # Attendance, Expense, LeaveRequest, PerformanceReview
        for tname in ["Attendance", "Expense", "LeaveRequest", "PerformanceReview"]:
            t_content = f"""table {tname}
\tcolumn ID
\t\tdataType: int64
\t\tsourceColumn: ID

\tpartition {tname} = m
\t\tmode: import
\t\tsource = Sql.Database("sql-workforce.database.windows.net", "WorkforceDW")
"""
            zf.writestr(f"WorkforceAnalytics.SemanticModel/definition/tables/{tname}.tmdl", t_content)

        # 2. System Date Tables (2 tables)
        loc_date_tmdl = """table LocalDateTable_a1b2c3d4-5678-90ef-1234-567890abcdef
\tisHidden
\tannotation __PBI_LocalDateTable = true

\tcolumn Date
\t\tdataType: dateTime
\t\tisHidden
\t\tsourceColumn: Date

\tcolumn Year = YEAR([Date])
\t\tdataType: int64
\t\tisHidden

\tcolumn Month = FORMAT([Date], "mmmm")
\t\tdataType: string
\t\tisHidden

\tpartition LocalDateTable = calculated
\t\tmode: import
\t\tsource = CALENDAR(DATE(2020,1,1), DATE(2030,12,31))
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/LocalDateTable_a1b2c3d4.tmdl", loc_date_tmdl)

        template_date_tmdl = """table DateTableTemplate_b2c3d4e5-6789-01fa-2345-678901abcdef
\tisHidden
\tannotation __PBI_TemplateDateTable = true

\tcolumn Date
\t\tdataType: dateTime
\t\tisHidden
\t\tsourceColumn: Date

\tpartition DateTableTemplate = calculated
\t\tmode: import
\t\tsource = CALENDAR(DATE(2020,1,1), DATE(2030,12,31))
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/tables/DateTableTemplate_b2c3d4e5.tmdl", template_date_tmdl)

        # 3. Relationships
        rels_tmdl = """relationship rel-emp-dept
\tfromColumn: Employee.DepartmentID
\ttoColumn: Department.DepartmentID
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-emp-manager
\tfromColumn: Employee.ManagerID
\ttoColumn: Employee.EmployeeID
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-empproj-emp
\tfromColumn: EmployeeProject.EmployeeID
\ttoColumn: Employee.EmployeeID
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-empproj-proj
\tfromColumn: EmployeeProject.ProjectID
\ttoColumn: Project.ProjectID
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-timesheet-emp
\tfromColumn: Timesheet.EmployeeID
\ttoColumn: Employee.EmployeeID
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-timesheet-cal
\tfromColumn: Timesheet.Date
\ttoColumn: Calendar.CalendarDate
\tcardinality: manyToOne
\tcrossFilteringBehavior: oneDirection
\tisActive: true

relationship rel-proj-startdate
\tfromColumn: Calendar.CalendarDate
\ttoColumn: Project.StartDate
\tcardinality: oneToMany
\tcrossFilteringBehavior: oneDirection
\tisActive: false

relationship rel-proj-enddate
\tfromColumn: Calendar.CalendarDate
\ttoColumn: Project.EndDate
\tcardinality: oneToMany
\tcrossFilteringBehavior: oneDirection
\tisActive: false
"""
        zf.writestr("WorkforceAnalytics.SemanticModel/definition/relationships.tmdl", rels_tmdl)

        # 4. Report definition (PBIR)
        zf.writestr("WorkforceAnalytics.Report/definition.pbir", json.dumps({"version": "1.0"}))

        # Page 1: Overview
        p1 = {"name": "WorkforceOverview", "displayName": "Workforce Overview"}
        zf.writestr("WorkforceAnalytics.Report/definition/pages/WorkforceOverview/page.json", json.dumps(p1))

        # Visual 1 (card: [Billable %])
        v1 = {
            "name": "v1_billable_pct",
            "visual": {
                "visualType": "card",
                "title": "Billable Efficiency",
                "query": {"queryState": {"Values": {"projections": [{"queryRef": "Timesheet.Billable %"}]}}}
            }
        }
        zf.writestr("WorkforceAnalytics.Report/definition/pages/WorkforceOverview/visuals/v1/visual.json", json.dumps(v1))

        # Visual 2 (lineChart: Calendar[CalendarDate] & [Total Hours])
        v2 = {
            "name": "v2_hours_trend",
            "visual": {
                "visualType": "lineChart",
                "title": "Monthly Hours Trend",
                "query": {
                    "queryState": {
                        "Category": {"projections": [{"queryRef": "Calendar.CalendarDate"}]},
                        "Y": {"projections": [{"queryRef": "Timesheet.Total Hours"}]}
                    }
                }
            }
        }
        zf.writestr("WorkforceAnalytics.Report/definition/pages/WorkforceOverview/visuals/v2/visual.json", json.dumps(v2))

        # Visual 3 (card: [Total Hours])
        v3 = {
            "name": "v3_total_hours",
            "visual": {
                "visualType": "card",
                "title": "Total Hours Card",
                "query": {"queryState": {"Values": {"projections": [{"queryRef": "Timesheet.Total Hours"}]}}}
            }
        }
        zf.writestr("WorkforceAnalytics.Report/definition/pages/WorkforceOverview/visuals/v3/visual.json", json.dumps(v3))

        # Page 2: Project Analysis
        p2 = {"name": "ProjectAnalysis", "displayName": "Project Analysis"}
        zf.writestr("WorkforceAnalytics.Report/definition/pages/ProjectAnalysis/page.json", json.dumps(p2))

        # Visual 4 (tableEx: Project[ProjectName], [Project Start Count], [Project End Count])
        v4 = {
            "name": "v4_proj_table",
            "visual": {
                "visualType": "tableEx",
                "title": "Project Timeline Analysis",
                "query": {
                    "queryState": {
                        "Values": {
                            "projections": [
                                {"queryRef": "Project.ProjectName"},
                                {"queryRef": "Project.Project Start Count"},
                                {"queryRef": "Project.Project End Count"}
                            ]
                        }
                    }
                }
            }
        }
        zf.writestr("WorkforceAnalytics.Report/definition/pages/ProjectAnalysis/visuals/v4/visual.json", json.dumps(v4))

        # Page 3: Employee Performance
        p3 = {"name": "EmployeePerf", "displayName": "Employee Performance"}
        zf.writestr("WorkforceAnalytics.Report/definition/pages/EmployeePerf/page.json", json.dumps(p3))

        # Visual 5 (tableEx: Employee[EmployeeName], [Profitability Indicator], [Total Hours])
        v5 = {
            "name": "v5_staff_perf",
            "visual": {
                "visualType": "tableEx",
                "title": "Staff Profitability",
                "query": {
                    "queryState": {
                        "Values": {
                            "projections": [
                                {"queryRef": "Employee.EmployeeName"},
                                {"queryRef": "Timesheet.Profitability Indicator"},
                                {"queryRef": "Timesheet.Total Hours"}
                            ]
                        }
                    }
                }
            }
        }
        zf.writestr("WorkforceAnalytics.Report/definition/pages/EmployeePerf/visuals/v5/visual.json", json.dumps(v5))

        # Page 4: Department Summary
        p4 = {"name": "DeptSummary", "displayName": "Department Summary"}
        zf.writestr("WorkforceAnalytics.Report/definition/pages/DeptSummary/page.json", json.dumps(p4))

    return output_path
