
  create view "postgres"."public_public"."int_transactions_cleaned__dbt_tmp"
    
    
  as (
    with source as (
    select * from "postgres"."public_public"."stg_transactional" 
),
cleaned as (
    select 
        cast(date as date) as transaction_date,
        date_trunc('month', cast(date as date)) as transaction_month,
        date_trunc('year', cast(date as date)) as transaction_year,
        EXTRACT(DOW FROM cast(date as date))::int as day_of_week,
        lower(trim(merchant)) as merchant_name,
        lower(trim(category)) as category_name,
        abs(amount) as amount,
        case when is_credit = True then 'credit' else 'debit' end as transaction_type,
        count(*) over ( partition by date, merchant, amount) as duplicate_count
        from 
            source
        where   
            amount is not null 
            and amount > 0
            and merchant is not null
            and date is not null    
),
final as (
    select 
    transaction_date,
    transaction_month,
    transaction_year,
    day_of_week,
    merchant_name,
    category_name,
    amount,
    transaction_type,
    duplicate_count,
    case when duplicate_count>1 then 1 else 0 end as is_potential_duplicate
    from 
    cleaned
)

select * from final
  );