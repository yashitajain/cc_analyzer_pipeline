
  create view "postgres"."public_public"."mart_anomalies__dbt_tmp"
    
    
  as (
    with transactions as (
    select * from "postgres"."public_public"."int_transactions_cleaned"
    where transaction_type = 'debit'
),
category_stats as (
    select
        category_name,
    avg(amount) as category_mean,
    stddev(amount) as category_sd,
    count(*) as category_count
    from 
        transactions
    group by category_name
),
transactions_with_stats as (
    select 
    t.*,
    c.category_mean,
    c.category_sd,
    c.category_count
    from 
        transactions t
    left join
        category_stats c
    on c.category_name = t.category_name
),
anomaly_detection as (
    select 
        transaction_date,
        merchant_name,
        category_name,
        amount,
        category_mean,
        category_sd,
        category_count,
        case when category_sd is not null and category_sd>0
        then round((amount-category_mean)/category_sd,2) else null end as z_score,
        case when category_sd is not null and category_sd>0 and abs((amount-category_mean)/category_sd)>2 then True
        when category_count = 1 and amount>500 then True
        else False end as anomaly_flag,
        case when category_sd is not null and category_sd>0 and abs((amount-category_mean)/category_sd)>2 then 'High zscore: significantly above category average'
        when category_count = 1 and amount>500 then 'Single large transaction in category'
        else 'Normal' end as anomaly_reason
    from
        transactions_with_stats
),
final as (
    select  
        transaction_date,
        merchant_name,
        category_name,
        round(amount,2) as amount,
        round(category_mean,2) as category_mean,
        round(category_sd,2) as category_sd,
        z_score,
        anomaly_flag,
        anomaly_reason
    from 
        anomaly_detection
)
select * from final
order by anomaly_flag desc, z_score desc nulls last
  );